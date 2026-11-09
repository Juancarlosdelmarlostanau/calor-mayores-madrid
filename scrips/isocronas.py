"""Funciones de las isócronas: entorno de 15 minutos andando de cada centro de mayores, normal y confortable."""

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

from config import RUTA_RAW, RUTA_CLEAN, CRS_PROYECTO

RUTA_RED = RUTA_RAW + "osm/walk_graph_madrid.graphml"
RUTA_CENTROS = RUTA_CLEAN + "centros_mayores.gpkg"
RUTA_HEXAGONOS = RUTA_CLEAN + "hexagonos_h3.gpkg"

VELOCIDAD = 0.8
MINUTOS = 15
DISTANCIA_MAXIMA = VELOCIDAD * MINUTOS * 60
MARGEN_CALLE = 25
RADIO_SALIDA = 100
VALORES_ALFA = [1.25, 1.5, 2]


def cargar_red():
    """Carga la red peatonal, la pasa a metros y devuelve la red, sus cruces y sus tramos."""
    red = ox.load_graphml(RUTA_RED)
    red = ox.project_graph(red, to_crs=CRS_PROYECTO)
    nodos, tramos = ox.graph_to_gdfs(red)
    return red, nodos, tramos


def nodos_de_salida(punto, red, nodos):
    """Devuelve los cruces a menos de RADIO_SALIDA m del centro; si no hay ninguno, el más cercano."""
    posiciones = nodos.sindex.query(punto.buffer(RADIO_SALIDA), predicate="intersects")
    if len(posiciones) == 0:
        return [ox.distance.nearest_nodes(red, X=punto.x, Y=punto.y)]
    return list(nodos.index[posiciones])


def calcular_isocrona(punto, peso, red, nodos, tramos):
    """Devuelve el polígono de las calles alcanzadas desde la puerta del centro y el nº de cruces alcanzados."""
    salidas = nodos_de_salida(punto, red, nodos)
    red.add_node("puerta")
    for nodo in salidas:
        distancia = punto.distance(nodos.loc[nodo, "geometry"])
        red.add_edge("puerta", nodo, **{peso: distancia})

    alcanzados = nx.single_source_dijkstra_path_length(red, "puerta", cutoff=DISTANCIA_MAXIMA, weight=peso)
    red.remove_node("puerta")

    tramos_alcanzados = tramos[
        tramos.index.get_level_values("u").isin(alcanzados) &
        tramos.index.get_level_values("v").isin(alcanzados)
    ]
    return tramos_alcanzados.buffer(MARGEN_CALLE).union_all(), len(alcanzados) - 1


def isocronas_normales(centros, red, nodos, tramos):
    """Calcula la isócrona normal (solo distancia) de cada centro y su área."""
    nodos_salida, distancias_nodo = ox.distance.nearest_nodes(red, X=centros["x"], Y=centros["y"], return_dist=True)
    centros = centros.copy()
    centros["nodo"] = nodos_salida
    centros["dist_nodo"] = np.round(distancias_nodo, 1)

    poligonos = []
    n_nodos = []
    for punto in centros.geometry:
        poligono, n_alcanzados = calcular_isocrona(punto, "length", red, nodos, tramos)
        poligonos.append(poligono)
        n_nodos.append(n_alcanzados)

    isocronas = gpd.GeoDataFrame(
        centros[["codigo", "nombre", "tipo_centro", "plazas", "dist_nodo"]].copy(),
        geometry=poligonos,
        crs=CRS_PROYECTO
    )
    isocronas["n_nodos"] = n_nodos
    isocronas["area_km2"] = (isocronas.area / 1_000_000).round(3)
    return isocronas


def hexagonos_por_centro(isocronas, centros, hexagonos):
    """Relaciona cada centro con los hexágonos urbanos de su isócrona, incluido siempre el suyo propio."""
    centroides = gpd.GeoDataFrame(hexagonos[["h3"]], geometry=hexagonos.centroid, crs=CRS_PROYECTO)
    centros_hexagonos = gpd.sjoin(centroides, isocronas[["codigo", "geometry"]], how="inner", predicate="within")
    centros_hexagonos = centros_hexagonos[["codigo", "h3"]].reset_index(drop=True)

    hexagono_propio = gpd.sjoin(centros[["codigo", "geometry"]], hexagonos[["h3", "geometry"]], how="inner", predicate="within")
    hexagono_propio = hexagono_propio[["codigo", "h3"]]

    centros_hexagonos = pd.concat([centros_hexagonos, hexagono_propio], ignore_index=True)
    return centros_hexagonos.drop_duplicates().reset_index(drop=True)


def asignar_calor(tramos, hexagonos_todos, hexagonos):
    """Da a cada tramo la temperatura del hexágono de su punto medio y su calor de 0 a 1 (percentiles 5 y 95)."""
    tramos = tramos.copy()
    puntos_medios = gpd.GeoDataFrame(geometry=tramos.geometry.interpolate(0.5, normalized=True), crs=CRS_PROYECTO)
    puntos_medios = gpd.sjoin_nearest(puntos_medios, hexagonos_todos[["lst", "geometry"]], how="left")
    puntos_medios = puntos_medios[~puntos_medios.index.duplicated()]
    tramos["lst"] = puntos_medios["lst"]

    lst_p5 = hexagonos["lst"].quantile(0.05)
    lst_p95 = hexagonos["lst"].quantile(0.95)
    tramos["calor"] = ((tramos["lst"] - lst_p5) / (lst_p95 - lst_p5)).clip(0, 1)
    return tramos


def isocronas_confortables(isocronas, centros, red, nodos, tramos):
    """Añade el área y el % de confort con cada α, y devuelve los polígonos confortables de α = 1,5."""
    isocronas = isocronas.copy()
    poligonos_central = []

    for alfa in VALORES_ALFA:
        nombre_peso = f"coste_{alfa}"
        tramos[nombre_peso] = tramos["length"] * (1 + (alfa - 1) * tramos["calor"])
        nx.set_edge_attributes(red, tramos[nombre_peso].to_dict(), nombre_peso)

        areas = []
        for punto in centros.geometry:
            poligono, _ = calcular_isocrona(punto, nombre_peso, red, nodos, tramos)
            areas.append(poligono.area / 1_000_000)
            if alfa == 1.5:
                poligonos_central.append(poligono)

        isocronas[f"area_conf_{alfa}"] = np.round(areas, 3)
        isocronas[f"pct_confort_{alfa}"] = (isocronas[f"area_conf_{alfa}"] / isocronas["area_km2"] * 100).round(1)

    confortables = gpd.GeoDataFrame(
        isocronas[["codigo", "nombre", "tipo_centro", "plazas", "area_km2", "area_conf_1.5", "pct_confort_1.5"]].copy(),
        geometry=poligonos_central,
        crs=CRS_PROYECTO
    )
    return isocronas, confortables


def calcular_isocronas():
    """Encadena todos los pasos y devuelve las isócronas normales, las confortables (α = 1,5) y la relación centro-hexágono."""
    red, nodos, tramos = cargar_red()
    centros = gpd.read_file(RUTA_CENTROS)
    hexagonos_todos = gpd.read_file(RUTA_HEXAGONOS)
    hexagonos = hexagonos_todos[hexagonos_todos["urbano"]].copy()

    isocronas = isocronas_normales(centros, red, nodos, tramos)
    centros_hexagonos = hexagonos_por_centro(isocronas, centros, hexagonos)

    tramos = asignar_calor(tramos, hexagonos_todos, hexagonos)
    isocronas, confortables = isocronas_confortables(isocronas, centros, red, nodos, tramos)
    return isocronas, confortables, centros_hexagonos