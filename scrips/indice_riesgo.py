"""Funciones del índice de riesgo: peligro, exposición, vulnerabilidad y capacidad del entorno de cada centro."""

import glob

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from config import RUTA_RAW, RUTA_CLEAN, CRS_PROYECTO
from isocronas import cargar_red, nodos_de_salida
import osmnx as ox

LIMITE_SERVICIOS = 1000
ESCALA_TIPO = {"residencia": 1.0, "centro de día": 0.75, "vivienda tutelada": 0.5, "centro de mayores": 0.25}
TIPOS_SALUD = {
    "/contenido/entidadesYorganismos/CentrosAtencionMedica/CentrosSalud": "centro de salud",
    "/contenido/entidadesYorganismos/CentrosAtencionMedica/HospitalesClinicasSanatorios": "hospital"
}


def cargar_servicios(centros):
    """Carga y filtra las fuentes, los centros de salud y los refugios (centros de mayores y mercados)."""
    fuentes = pd.read_csv(glob.glob(RUTA_RAW + "fuentes/*.csv")[0], sep=";", encoding="utf-8")
    fuentes = fuentes[(fuentes["ESTADO"] == "OPERATIVO") & (fuentes["USO"].isin(["PERSONAS", "PERSONAS_Y_MASCOTAS"]))]
    fuentes = gpd.GeoDataFrame(fuentes[["ID", "UBICACION"]].copy(),
                               geometry=gpd.points_from_xy(fuentes["COORD_GIS_X"], fuentes["COORD_GIS_Y"]),
                               crs=CRS_PROYECTO)

    salud = pd.read_csv(glob.glob(RUTA_RAW + "centrosalud/*.csv")[0], sep=";", encoding="latin-1")
    salud = salud[salud["TIPO"].isin(TIPOS_SALUD.keys())].copy()
    salud["tipo_salud"] = salud["TIPO"].map(TIPOS_SALUD)
    salud = salud.dropna(subset=["COORDENADA-X", "COORDENADA-Y"])
    salud = gpd.GeoDataFrame(salud[["PK", "NOMBRE", "tipo_salud"]].copy(),
                             geometry=gpd.points_from_xy(salud["COORDENADA-X"], salud["COORDENADA-Y"]),
                             crs=CRS_PROYECTO)

    mercados = pd.read_csv(glob.glob(RUTA_RAW + "mercados/*.csv")[0], sep=";", encoding="latin-1")
    mercados = mercados.dropna(subset=["COORDENADA-X", "COORDENADA-Y"])
    mercados = gpd.GeoDataFrame(mercados[["PK", "NOMBRE"]].copy(),
                                geometry=gpd.points_from_xy(mercados["COORDENADA-X"], mercados["COORDENADA-Y"]),
                                crs=CRS_PROYECTO)

    refugios_mayores = centros[centros["tipo_centro"] == "centro de mayores"][["codigo", "nombre", "geometry"]].copy()
    refugios_mayores["tipo_refugio"] = "centro de mayores"
    refugios_mercados = mercados.rename(columns={"PK": "codigo", "NOMBRE": "nombre"})
    refugios_mercados["tipo_refugio"] = "mercado"
    refugios = pd.concat([refugios_mayores, refugios_mercados], ignore_index=True)
    refugios["codigo"] = refugios["codigo"].astype(str)
    return fuentes, salud, refugios


def crear_indice(centros):
    """Crea la tabla del índice con el confort, la temperatura y la copa de la isócrona de cada centro."""
    isocronas = gpd.read_file(RUTA_CLEAN + "isocronas_normales.gpkg")
    centros_hexagonos = pd.read_csv(RUTA_CLEAN + "centros_hexagonos.csv")
    hexagonos_todos = gpd.read_file(RUTA_CLEAN + "hexagonos_h3.gpkg")

    indice = centros[["codigo", "nombre", "tipo_centro", "plazas", "titularidad", "geometry"]].copy()
    indice = indice.merge(isocronas[["codigo", "pct_confort_1.5"]], on="codigo", how="left")

    hexagonos_isocrona = centros_hexagonos.merge(hexagonos_todos[["h3", "lst", "pct_copa"]], on="h3", how="left")
    resumen_isocrona = hexagonos_isocrona.groupby("codigo").agg(
        lst_isocrona=("lst", "mean"),
        copa_isocrona=("pct_copa", "mean")
    ).reset_index()
    return indice.merge(resumen_isocrona, on="codigo", how="left")


def agregar_exposicion_vulnerabilidad(indice):
    """Añade la exposición (plazas por tipo) y la vulnerabilidad (tipo de centro y antigüedad del edificio)."""
    indice["exposicion"] = indice.groupby("tipo_centro")["plazas"].rank(pct=True)
    indice["vulnerabilidad_tipo"] = indice["tipo_centro"].map(ESCALA_TIPO)

    edificios = gpd.read_file(RUTA_RAW + "dato6/catastro_edificios.gpkg", columns=["beginning"])
    edificios["anio"] = pd.to_numeric(edificios["beginning"].astype(str).str[:4], errors="coerce")
    edificio_centro = gpd.sjoin_nearest(indice[["codigo", "geometry"]], edificios[["anio", "geometry"]],
                                        how="left", max_distance=50, distance_col="dist_edificio")
    edificio_centro = edificio_centro.drop_duplicates(subset="codigo")
    indice["anio_edificio"] = edificio_centro["anio"].values

    indice["anio_edificio"] = indice["anio_edificio"].fillna(indice["anio_edificio"].median())
    indice["vulnerabilidad_edificio"] = indice["anio_edificio"].rank(pct=True, ascending=False)
    indice["vulnerabilidad"] = (indice["vulnerabilidad_tipo"] + indice["vulnerabilidad_edificio"]) / 2
    return indice


def distancias_desde_puerta(punto, limite, red, nodos):
    """Devuelve un diccionario con la distancia por la red desde la puerta del centro a cada cruce alcanzado."""
    salidas = nodos_de_salida(punto, red, nodos)
    red.add_node("puerta")
    for nodo in salidas:
        distancia = punto.distance(nodos.loc[nodo, "geometry"])
        red.add_edge("puerta", nodo, length=distancia)

    alcanzados = nx.single_source_dijkstra_path_length(red, "puerta", cutoff=limite, weight="length")
    red.remove_node("puerta")
    alcanzados.pop("puerta")
    return alcanzados


def agregar_distancias(indice, fuentes, salud, refugios, red, nodos):
    """Añade la distancia andando desde cada centro a la fuente, el refugio y el centro sanitario más cercanos."""
    indice["nodo"] = ox.distance.nearest_nodes(red, X=indice.geometry.x, Y=indice.geometry.y)
    fuentes["nodo"] = ox.distance.nearest_nodes(red, X=fuentes.geometry.x, Y=fuentes.geometry.y)
    salud["nodo"] = ox.distance.nearest_nodes(red, X=salud.geometry.x, Y=salud.geometry.y)
    refugios["nodo"] = ox.distance.nearest_nodes(red, X=refugios.geometry.x, Y=refugios.geometry.y)
    nodos_fuentes = set(fuentes["nodo"])
    nodos_salud = set(salud["nodo"])

    dist_agua, dist_refugio, dist_salud = [], [], []
    for codigo, punto in zip(indice["codigo"], indice.geometry):
        alcanzados = distancias_desde_puerta(punto, LIMITE_SERVICIOS, red, nodos)

        cruces_agua = nodos_fuentes & alcanzados.keys()
        dist_agua.append(min(alcanzados[n] for n in cruces_agua) if cruces_agua else np.nan)

        cruces_salud = nodos_salud & alcanzados.keys()
        dist_salud.append(min(alcanzados[n] for n in cruces_salud) if cruces_salud else np.nan)

        otros_refugios = refugios[(refugios["codigo"] != str(codigo)) & (refugios["nodo"].isin(alcanzados.keys()))]
        dist_refugio.append(min(alcanzados[n] for n in otros_refugios["nodo"]) if len(otros_refugios) > 0 else np.nan)

    indice["dist_agua"] = dist_agua
    indice["dist_refugio"] = dist_refugio
    indice["dist_salud"] = dist_salud
    return indice


def calcular_capacidad(tabla, limite):
    """Devuelve la capacidad de cada centro (0 a 1) con las distancias limitadas al valor dado."""
    indicadores = pd.DataFrame(index=tabla.index)
    for servicio in ["dist_agua", "dist_refugio", "dist_salud"]:
        distancia = tabla[servicio].fillna(limite).clip(upper=limite)
        indicadores[servicio] = distancia.rank(pct=True, ascending=False)
    indicadores["sombra"] = tabla["copa_isocrona"].rank(pct=True)
    indicadores["confort"] = tabla["pct_confort_1.5"].rank(pct=True)
    return indicadores.mean(axis=1)


def agregar_riesgo(indice):
    """Añade el peligro, la capacidad, el riesgo (con 1.000 y 720 m) y la prioridad por percentiles."""
    indice["peligro"] = indice["lst_isocrona"].rank(pct=True)
    indice["capacidad"] = calcular_capacidad(indice, LIMITE_SERVICIOS)
    indice["capacidad_720"] = calcular_capacidad(indice, 720)

    indice["riesgo"] = indice["peligro"] * indice["exposicion"] * indice["vulnerabilidad"] * (1 - indice["capacidad"])
    indice["riesgo_720"] = indice["peligro"] * indice["exposicion"] * indice["vulnerabilidad"] * (1 - indice["capacidad_720"])

    corte_medio = indice["riesgo"].quantile(0.5)
    corte_alto = indice["riesgo"].quantile(0.8)
    indice["prioridad"] = pd.cut(indice["riesgo"], bins=[-np.inf, corte_medio, corte_alto, np.inf],
                                 labels=["baja", "media", "alta"])
    return indice


def calcular_indice():
    """Encadena todos los pasos y devuelve el índice de riesgo y las capas de servicios."""
    centros = gpd.read_file(RUTA_CLEAN + "centros_mayores.gpkg")
    fuentes, salud, refugios = cargar_servicios(centros)
    red, nodos, _ = cargar_red()

    indice = crear_indice(centros)
    indice = agregar_exposicion_vulnerabilidad(indice)
    indice = agregar_distancias(indice, fuentes, salud, refugios, red, nodos)
    indice = agregar_riesgo(indice)
    return indice, fuentes, salud, refugios