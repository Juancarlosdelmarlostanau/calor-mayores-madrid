"""Funciones de la priorización: diagnóstico con SHAP, optimizador de hexágonos y efecto del plan en cada centro."""

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shap

from config import RUTA_CLEAN, CRS_PROYECTO
from simulador import cargar_modelo, preparar_hexagonos, calcular_limites, simular_escenarios
from isocronas import cargar_red, calcular_isocrona

PRESUPUESTO = 50
ALFA = 1.5
FASES = ["hoy", "bajo", "moderado", "ambicioso"]
COLUMNAS_BAJADA = ["bajada_bajo", "bajada_moderado", "bajada_ambicioso"]
COLUMNAS_PLAN = ["plan_bajo", "plan_moderado", "plan_ambicioso"]
PALANCAS = {
    "vegetacion": ["ndvi", "pct_copa", "altura_arboles", "arboles_ha"],
    "suelo_desnudo": ["pct_suelo_desnudo"],
    "edificios": ["pct_edificado", "plantas_media", "anio_medio", "pct_industrial", "albedo"],
    "parques": ["dist_parque_grande"]
}


def diagnosticar(candidatos, modelo, features, centros_hexagonos, indice):
    """Suma los valores SHAP por palanca, hace la media en la isócrona de cada centro y elige la medida recomendada."""
    explicador = shap.TreeExplainer(modelo)
    valores_shap = explicador(candidatos[features])

    shap_hexagonos = pd.DataFrame(valores_shap.values, columns=features)
    shap_hexagonos["h3"] = candidatos["h3"].values
    for palanca, columnas in PALANCAS.items():
        shap_hexagonos[palanca] = shap_hexagonos[columnas].sum(axis=1)

    diagnostico = centros_hexagonos.merge(shap_hexagonos[["h3"] + list(PALANCAS)], on="h3", how="left")
    diagnostico = diagnostico.groupby("codigo")[list(PALANCAS)].mean().reset_index()
    diagnostico["medida"] = diagnostico[list(PALANCAS)].idxmax(axis=1)
    diagnostico.loc[diagnostico[list(PALANCAS)].max(axis=1) <= 0, "medida"] = "ninguna"
    return diagnostico.merge(indice[["codigo", "nombre", "tipo_centro", "prioridad"]], on="codigo", how="left")


def simular_candidatos(candidatos, modelo, features, pendiente_ndvi, ndvi_maximo):
    """Simula las tres fases en los candidatos y deja en 0 las bajadas negativas."""
    candidatos = simular_escenarios(candidatos, modelo, features, pendiente_ndvi, ndvi_maximo)
    for columna in COLUMNAS_BAJADA:
        candidatos[columna] = candidatos[columna].clip(lower=0)
    return candidatos


def valorar_hexagonos(candidatos, centros_hexagonos, indice):
    """Añade el riesgo sumado de los centros de cada hexágono y su valor (bajada moderada × riesgo)."""
    riesgo_hexagonos = centros_hexagonos.merge(indice[["codigo", "riesgo"]], on="codigo", how="left")
    riesgo_hexagonos = riesgo_hexagonos.groupby("h3").agg(
        riesgo_hexagono=("riesgo", "sum"),
        n_centros=("codigo", "size")
    ).reset_index()
    candidatos = candidatos.merge(riesgo_hexagonos, on="h3", how="left")
    candidatos["valor"] = candidatos["bajada_moderado"] * candidatos["riesgo_hexagono"]
    return candidatos


def calcular_curva(candidatos):
    """Valor acumulado del optimizador y media de 100 selecciones al azar, de 10 a 200 hexágonos."""
    candidatos_ordenados = candidatos.sort_values("valor", ascending=False)
    tamanos = list(range(10, 201, 10))
    valor_optimizador = []
    valor_azar = []
    for n in tamanos:
        valor_optimizador.append(candidatos_ordenados["valor"].head(n).sum())
        sumas_aleatorias = []
        for semilla in range(100):
            sumas_aleatorias.append(candidatos["valor"].sample(n, random_state=semilla).sum())
        valor_azar.append(np.mean(sumas_aleatorias))

    curva = pd.DataFrame({"hexagonos": tamanos, "optimizador": valor_optimizador, "azar": valor_azar})
    curva["veces_mejor"] = curva["optimizador"] / curva["azar"]
    return curva


def aplicar_plan(candidatos):
    """Marca los hexágonos elegidos por el optimizador y su bajada en el plan (0 en los no elegidos)."""
    seleccion = candidatos.nlargest(PRESUPUESTO, "valor")
    candidatos["elegido"] = candidatos["h3"].isin(seleccion["h3"])
    for columna_bajada, columna_plan in zip(COLUMNAS_BAJADA, COLUMNAS_PLAN):
        candidatos[columna_plan] = candidatos[columna_bajada].where(candidatos["elegido"], 0)
    return candidatos


def calcular_antes_despues(candidatos, centros_hexagonos, indice):
    """Bajada media de la isócrona de cada centro (plan y potencial máximo) y temperatura después de cada fase."""
    antes_despues = centros_hexagonos.merge(candidatos[["h3"] + COLUMNAS_PLAN + COLUMNAS_BAJADA], on="h3", how="left")
    antes_despues = antes_despues.groupby("codigo")[COLUMNAS_PLAN + COLUMNAS_BAJADA].mean().reset_index()
    antes_despues = antes_despues.merge(indice[["codigo", "nombre", "tipo_centro", "prioridad", "lst_isocrona"]],
                                        on="codigo", how="left")
    for columna_plan in COLUMNAS_PLAN:
        antes_despues[columna_plan.replace("plan", "lst_despues")] = antes_despues["lst_isocrona"] - antes_despues[columna_plan]
    return antes_despues


def preparar_tramos_plan(tramos, red, hexagonos_todos, hexagonos, candidatos):
    """Da a cada tramo su temperatura y su hexágono, y añade a la red el coste de hoy y de cada fase del plan."""
    tramos = tramos.copy()
    puntos_medios = gpd.GeoDataFrame(geometry=tramos.geometry.interpolate(0.5, normalized=True), crs=CRS_PROYECTO)
    puntos_medios = gpd.sjoin_nearest(puntos_medios, hexagonos_todos[["h3", "lst", "geometry"]], how="left")
    puntos_medios = puntos_medios[~puntos_medios.index.duplicated()]
    tramos["lst"] = puntos_medios["lst"]
    tramos["h3"] = puntos_medios["h3"]

    bajadas_plan = candidatos.set_index("h3")[COLUMNAS_PLAN]
    for columna_plan in COLUMNAS_PLAN:
        tramos[columna_plan] = tramos["h3"].map(bajadas_plan[columna_plan]).fillna(0)

    lst_p5 = hexagonos["lst"].quantile(0.05)
    lst_p95 = hexagonos["lst"].quantile(0.95)
    for fase in FASES:
        if fase == "hoy":
            lst_fase = tramos["lst"]
        else:
            lst_fase = tramos["lst"] - tramos[f"plan_{fase}"]
        calor = ((lst_fase - lst_p5) / (lst_p95 - lst_p5)).clip(0, 1)
        tramos[f"coste_{fase}"] = tramos["length"] * (1 + (ALFA - 1) * calor)
        nx.set_edge_attributes(red, tramos[f"coste_{fase}"].to_dict(), f"coste_{fase}")
    return tramos


def calcular_confort_plan(antes_despues, indice, red, nodos, tramos):
    """Recalcula la isócrona confortable de los centros que mejoran, hoy y en cada fase, y los puntos de confort que ganan."""
    isocronas_normales = gpd.read_file(RUTA_CLEAN + "isocronas_normales.gpkg")
    codigos_mejoran = antes_despues.loc[antes_despues["plan_moderado"] > 0, "codigo"]

    confort = indice[indice["codigo"].isin(codigos_mejoran)][["codigo", "nombre", "tipo_centro", "prioridad",
                                                               "nodo", "pct_confort_1.5", "geometry"]]
    confort = confort.merge(isocronas_normales[["codigo", "area_km2"]], on="codigo", how="left").reset_index(drop=True)

    poligonos_fases = {}
    for fase in FASES:
        poligonos = []
        areas = []
        for punto in confort.geometry:
            poligono, _ = calcular_isocrona(punto, f"coste_{fase}", red, nodos, tramos)
            poligonos.append(poligono)
            areas.append(poligono.area / 1_000_000)
        poligonos_fases[fase] = poligonos
        confort[f"pct_confort_{fase}"] = (np.round(areas, 3) / confort["area_km2"] * 100).round(1)

    for fase in ["bajo", "moderado", "ambicioso"]:
        confort[f"gana_{fase}"] = confort[f"pct_confort_{fase}"] - confort["pct_confort_hoy"]

    tablas_fases = []
    for fase in FASES:
        tabla_fase = gpd.GeoDataFrame(confort[["codigo", "nombre", "prioridad"]].copy(),
                                      geometry=poligonos_fases[fase], crs=CRS_PROYECTO)
        tabla_fase["fase"] = fase
        tabla_fase["pct_confort"] = confort[f"pct_confort_{fase}"]
        tablas_fases.append(tabla_fase)
    isocronas_plan = pd.concat(tablas_fases, ignore_index=True)
    return confort, isocronas_plan


def calcular_priorizacion():
    """Encadena todos los pasos y devuelve el diagnóstico, los candidatos, la curva, el antes y después, el confort y las isócronas del plan."""
    modelo, features, mediana_anio_train = cargar_modelo()
    hexagonos = preparar_hexagonos(mediana_anio_train)
    pendiente_ndvi, ndvi_maximo = calcular_limites(hexagonos)
    centros_hexagonos = pd.read_csv(RUTA_CLEAN + "centros_hexagonos.csv")
    indice = gpd.read_file(RUTA_CLEAN + "indice_riesgo.gpkg")
    candidatos = hexagonos[hexagonos["h3"].isin(centros_hexagonos["h3"])].copy()

    diagnostico = diagnosticar(candidatos, modelo, features, centros_hexagonos, indice)
    candidatos = simular_candidatos(candidatos, modelo, features, pendiente_ndvi, ndvi_maximo)
    candidatos = valorar_hexagonos(candidatos, centros_hexagonos, indice)
    curva = calcular_curva(candidatos)
    candidatos = aplicar_plan(candidatos)
    antes_despues = calcular_antes_despues(candidatos, centros_hexagonos, indice)

    red, nodos, tramos = cargar_red()
    hexagonos_todos = gpd.read_file(RUTA_CLEAN + "hexagonos_h3.gpkg")
    tramos = preparar_tramos_plan(tramos, red, hexagonos_todos, hexagonos, candidatos)
    confort, isocronas_plan = calcular_confort_plan(antes_despues, indice, red, nodos, tramos)
    return diagnostico, candidatos, curva, antes_despues, confort, isocronas_plan