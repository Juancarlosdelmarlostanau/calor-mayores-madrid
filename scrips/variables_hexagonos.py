"""Funciones para crear la malla de hexágonos H3 de Madrid y calcular sus variables."""

import glob

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterstats import zonal_stats
from shapely.geometry import Polygon

from config import RUTA_RAW, RUTA_CLEAN, CRS_PROYECTO

RESOLUCION_H3 = 9
ALTURA_MAXIMA_ARBOL = 40
AREA_MINIMA_PARQUE_HA = 1
CODIGOS_VIARIO = ["12210", "12220"]
CODIGO_FERROCARRIL = "12230"
CODIGO_AGUA = "50000"

RUTA_TERMINO = RUTA_RAW + "limites/Termino_municipal/TERMINO_MUNICIPAL.shp"
RUTA_BARRIOS = RUTA_RAW + "limites/Barrios/BARRIOS.shp"
RUTA_CENTROS = RUTA_CLEAN + "centros_mayores.gpkg"
RUTA_LST = RUTA_RAW + "dato4y5/lst_summer_madrid_2023_2026.tif"
RUTA_NDVI = RUTA_RAW + "dato4y5/ndvi_summer_madrid_2023_2026.tif"
RUTA_ALBEDO = RUTA_RAW + "dato4y5/albedo_summer_madrid_2023_2026.tif"
RUTA_EDIFICIOS = RUTA_RAW + "dato6/catastro_edificios.gpkg"
RUTA_PARTES = RUTA_RAW + "dato6/catastro_partes.gpkg"
RUTA_MASCARA = RUTA_RAW + "dato7/7253/Results/CLMS_UA_STL_S2021_V005ha_ES001L3_MADRID_03035_V01_R02_20251121/CLMS_UA_UM_S2021_V005ha_ES001L3_MADRID_03035_V01_R02_20251121.fgb"
RUTA_COPA = RUTA_RAW + "dato7/7253/Results/CLMS_UA_STL_S2021_V005ha_ES001L3_MADRID_03035_V01_R02_20251121/CLMS_UA_STL_S2021_V005ha_ES001L3_MADRID_03035_V01_R02_20251121.fgb"
RUTA_USOS = RUTA_RAW + "dato7/9083/Results/CLMS_UA_LCU_S2021_V025ha_ES001L3_MADRID_03035_V01_R00_20241115/CLMS_UA_LCU_S2021_V025ha_ES001L3_MADRID_03035_V01_R00_20241115.fgb"
RUTA_ARBOLES = RUTA_RAW + "arbolado/300761-1-arbolado-especies-zip/ARBOLADO_MADRID.shp"
RUTA_PARQUES = RUTA_RAW + "osm/parks_madrid.gpkg"
PATRON_HOJAS_MDT = RUTA_RAW + "dato8/PNOA_MDT05_*.tif"
RUTA_MDT = RUTA_RAW + "dato8/mdt_madrid_25m.tif"


def crear_malla():
    """Crea los hexágonos H3 de resolución 9 que cubren el término municipal."""
    termino = gpd.read_file(RUTA_TERMINO)
    termino_wgs84 = termino.to_crs(epsg=4326)
    celdas = h3.geo_to_cells(termino_wgs84.geometry.iloc[0], res=RESOLUCION_H3)

    poligonos = []
    for celda in celdas:
        contorno = h3.cell_to_boundary(celda)
        vertices = [(lng, lat) for lat, lng in contorno]
        poligonos.append(Polygon(vertices))

    hexagonos = gpd.GeoDataFrame({"h3": list(celdas)}, geometry=poligonos, crs="EPSG:4326")
    return hexagonos.to_crs(CRS_PROYECTO)


def marcar_urbanos(hexagonos):
    """Marca como urbanos los hexágonos de la máscara urbana y los que contienen un centro de mayores."""
    hexagonos = hexagonos.copy()
    mascara = gpd.read_file(RUTA_MASCARA).to_crs(CRS_PROYECTO)
    mascara_union = mascara.union_all()
    hexagonos["urbano"] = hexagonos.centroid.within(mascara_union)

    centros = gpd.read_file(RUTA_CENTROS)
    centros_hex = gpd.sjoin(centros, hexagonos, how="left", predicate="within")
    hexagonos_con_centro = centros_hex["h3"].unique()
    hexagonos.loc[hexagonos["h3"].isin(hexagonos_con_centro), "urbano"] = True
    return hexagonos


def agregar_satelite(hexagonos):
    """Añade la temperatura de superficie, el NDVI y el albedo medios de cada hexágono."""
    hexagonos = hexagonos.copy()
    estadisticas_lst = zonal_stats(hexagonos, RUTA_LST, stats=["mean", "count"])
    hexagonos["lst"] = [e["mean"] for e in estadisticas_lst]
    hexagonos["lst_pixeles"] = [e["count"] for e in estadisticas_lst]

    estadisticas_ndvi = zonal_stats(hexagonos, RUTA_NDVI, stats=["mean"])
    hexagonos["ndvi"] = [e["mean"] for e in estadisticas_ndvi]

    estadisticas_albedo = zonal_stats(hexagonos, RUTA_ALBEDO, stats=["mean"])
    hexagonos["albedo"] = [e["mean"] for e in estadisticas_albedo]
    return hexagonos


def agregar_catastro(hexagonos):
    """Añade el % edificado, el % industrial, la edificabilidad, las plantas medias y el año medio."""
    hexagonos_base = hexagonos[["h3", "geometry"]]

    edificios = gpd.read_file(RUTA_EDIFICIOS, columns=["localId", "currentUse", "beginning"])
    partes = gpd.read_file(RUTA_PARTES, columns=["localId", "numberOfFloorsAboveGround"])
    edificios["anio"] = pd.to_numeric(edificios["beginning"].astype(str).str[:4], errors="coerce")
    partes["plantas"] = partes["numberOfFloorsAboveGround"]

    edificios_trozos = gpd.overlay(edificios[["currentUse", "anio", "geometry"]], hexagonos_base, how="intersection")
    edificios_trozos["area"] = edificios_trozos.area
    edificios_trozos["area_industrial"] = edificios_trozos["area"].where(edificios_trozos["currentUse"] == "3_industrial", 0)
    edificios_trozos["anio_x_area"] = edificios_trozos["anio"] * edificios_trozos["area"]
    edificios_trozos["area_con_anio"] = edificios_trozos["area"].where(edificios_trozos["anio"].notnull(), 0)

    partes_trozos = gpd.overlay(partes[["plantas", "geometry"]], hexagonos_base, how="intersection")
    partes_trozos["area"] = partes_trozos.area
    partes_trozos["superficie_construida"] = partes_trozos["area"] * partes_trozos["plantas"]
    partes_trozos["plantas_x_area"] = partes_trozos["plantas"] * partes_trozos["area"]
    partes_trozos["area_con_plantas"] = partes_trozos["area"].where(partes_trozos["plantas"] > 0, 0)

    resumen_edificios = edificios_trozos.groupby("h3")[["area", "area_industrial", "anio_x_area", "area_con_anio"]].sum()
    resumen_partes = partes_trozos.groupby("h3")[["superficie_construida", "plantas_x_area", "area_con_plantas"]].sum()

    hexagonos = hexagonos.merge(resumen_edificios, on="h3", how="left")
    hexagonos = hexagonos.merge(resumen_partes, on="h3", how="left")

    area_hexagono = hexagonos.area
    hexagonos["pct_edificado"] = (hexagonos["area"].fillna(0) / area_hexagono * 100).round(2)
    hexagonos["pct_industrial"] = (hexagonos["area_industrial"].fillna(0) / area_hexagono * 100).round(2)
    hexagonos["edificabilidad"] = (hexagonos["superficie_construida"].fillna(0) / area_hexagono).round(3)
    hexagonos["plantas_media"] = (hexagonos["plantas_x_area"] / hexagonos["area_con_plantas"]).round(2)
    hexagonos["anio_medio"] = (hexagonos["anio_x_area"] / hexagonos["area_con_anio"]).round(0)

    return hexagonos.drop(columns=["area", "area_industrial", "anio_x_area", "area_con_anio",
                                   "superficie_construida", "plantas_x_area", "area_con_plantas"])


def agregar_vegetacion(hexagonos):
    """Añade el % de copa de árboles (Urban Atlas) y la densidad y altura del arbolado municipal."""
    hexagonos_base = hexagonos[["h3", "geometry"]]

    copa = gpd.read_file(RUTA_COPA).to_crs(CRS_PROYECTO)
    copa_trozos = gpd.overlay(copa[["geometry"]], hexagonos_base, how="intersection")
    copa_trozos["area_copa"] = copa_trozos.area
    resumen_copa = copa_trozos.groupby("h3")[["area_copa"]].sum()
    hexagonos = hexagonos.merge(resumen_copa, on="h3", how="left")
    hexagonos["pct_copa"] = (hexagonos["area_copa"].fillna(0) / hexagonos.area * 100).round(2)
    hexagonos = hexagonos.drop(columns=["area_copa"])

    arboles = gpd.read_file(RUTA_ARBOLES, columns=["ALTURA_TOT"])
    arboles.loc[(arboles["ALTURA_TOT"] > ALTURA_MAXIMA_ARBOL) | (arboles["ALTURA_TOT"] == 0), "ALTURA_TOT"] = np.nan
    arboles_hex = gpd.sjoin(arboles, hexagonos_base, how="inner", predicate="within")
    resumen_arboles = arboles_hex.groupby("h3").agg(
        n_arboles=("ALTURA_TOT", "size"),
        altura_arboles=("ALTURA_TOT", "mean")
    )
    hexagonos = hexagonos.merge(resumen_arboles, on="h3", how="left")
    hexagonos["arboles_ha"] = (hexagonos["n_arboles"].fillna(0) / (hexagonos.area / 10000)).round(1)
    hexagonos["altura_arboles"] = hexagonos["altura_arboles"].round(2)
    return hexagonos.drop(columns=["n_arboles"])


def crear_mosaico_mdt(hexagonos):
    """Une las hojas del MDT05 en un mosaico de 25 m recortado al área de los hexágonos."""
    hojas_mdt = glob.glob(PATRON_HOJAS_MDT)
    fuentes = [rasterio.open(hoja) for hoja in hojas_mdt]
    mosaico, transformacion = merge(fuentes, bounds=tuple(hexagonos.total_bounds), res=25)

    perfil = fuentes[0].profile
    perfil.update(height=mosaico.shape[1], width=mosaico.shape[2], transform=transformacion)
    with rasterio.open(RUTA_MDT, "w", **perfil) as destino:
        destino.write(mosaico)

    for fuente in fuentes:
        fuente.close()


def agregar_elevacion(hexagonos):
    """Añade la altitud media de cada hexágono a partir del mosaico del MDT."""
    hexagonos = hexagonos.copy()
    crear_mosaico_mdt(hexagonos)
    estadisticas_elevacion = zonal_stats(hexagonos, RUTA_MDT, stats=["mean"])
    hexagonos["elevacion"] = [e["mean"] for e in estadisticas_elevacion]
    hexagonos["elevacion"] = hexagonos["elevacion"].round(1)
    return hexagonos


def agregar_entorno(hexagonos):
    """Añade la distancia a parques grandes, el % de viario y de ferrocarril y la distancia al agua."""
    hexagonos_base = hexagonos[["h3", "geometry"]]
    centroides = gpd.GeoDataFrame(hexagonos[["h3"]], geometry=hexagonos.centroid, crs=CRS_PROYECTO)

    parques = gpd.read_file(RUTA_PARQUES).to_crs(CRS_PROYECTO)
    parques["area_ha"] = parques.area / 10000
    barrios = gpd.read_file(RUTA_BARRIOS)
    casa_de_campo = barrios[barrios["NOMBRE"] == "Casa de Campo"][["geometry"]]
    parques_grandes = parques[parques["area_ha"] >= AREA_MINIMA_PARQUE_HA][["geometry"]]
    parques_grandes = pd.concat([parques_grandes, casa_de_campo], ignore_index=True)

    distancias = gpd.sjoin_nearest(centroides, parques_grandes[["geometry"]], distance_col="dist_parque_grande")
    distancias = distancias.drop_duplicates(subset="h3")
    hexagonos = hexagonos.merge(distancias[["h3", "dist_parque_grande"]], on="h3", how="left")
    hexagonos["dist_parque_grande"] = hexagonos["dist_parque_grande"].round(1)

    usos = gpd.read_file(RUTA_USOS, bbox=hexagonos)
    usos = usos.to_crs(CRS_PROYECTO)
    usos["code_2021"] = usos["code_2021"].astype(str)

    viario = usos[usos["code_2021"].isin(CODIGOS_VIARIO)][["geometry"]]
    ferrocarril = usos[usos["code_2021"] == CODIGO_FERROCARRIL][["geometry"]]
    viario_trozos = gpd.overlay(viario, hexagonos_base, how="intersection")
    viario_trozos["area_viario"] = viario_trozos.area
    ferrocarril_trozos = gpd.overlay(ferrocarril, hexagonos_base, how="intersection")
    ferrocarril_trozos["area_ferrocarril"] = ferrocarril_trozos.area

    hexagonos = hexagonos.merge(viario_trozos.groupby("h3")[["area_viario"]].sum(), on="h3", how="left")
    hexagonos = hexagonos.merge(ferrocarril_trozos.groupby("h3")[["area_ferrocarril"]].sum(), on="h3", how="left")
    hexagonos["pct_viario"] = (hexagonos["area_viario"].fillna(0) / hexagonos.area * 100).round(2)
    hexagonos["pct_ferrocarril"] = (hexagonos["area_ferrocarril"].fillna(0) / hexagonos.area * 100).round(2)
    hexagonos = hexagonos.drop(columns=["area_viario", "area_ferrocarril"])

    agua = usos[usos["code_2021"] == CODIGO_AGUA][["geometry"]]
    distancias_agua = gpd.sjoin_nearest(centroides, agua, distance_col="dist_agua")
    distancias_agua = distancias_agua.drop_duplicates(subset="h3")
    hexagonos = hexagonos.merge(distancias_agua[["h3", "dist_agua"]], on="h3", how="left")
    hexagonos["dist_agua"] = hexagonos["dist_agua"].round(1)
    return hexagonos


def crear_tabla_hexagonos():
    """Encadena todos los pasos y devuelve la tabla de hexágonos con la variable objetivo y las predictoras."""
    hexagonos = crear_malla()
    hexagonos = marcar_urbanos(hexagonos)
    hexagonos = agregar_satelite(hexagonos)
    hexagonos = agregar_catastro(hexagonos)
    hexagonos = agregar_vegetacion(hexagonos)
    hexagonos = agregar_elevacion(hexagonos)
    return agregar_entorno(hexagonos)