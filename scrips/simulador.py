"""Funciones del simulador de arbolado: temperatura del entorno de los centros con más copa de árboles."""

import geopandas as gpd
import joblib
import numpy as np
from sklearn.linear_model import LinearRegression

from config import RUTA_CLEAN

RUTA_MODELO = "../models/modelo_gradient_boosting.pkl"
RUTA_HEXAGONOS = RUTA_CLEAN + "hexagonos_h3.gpkg"
RUTA_CENTROS = RUTA_CLEAN + "centros_mayores.gpkg"
ESCENARIOS = {"bajo": 5, "moderado": 10, "ambicioso": 20}
COLUMNAS_RESULTADO = ["lst_actual", "bajada_bajo", "bajada_moderado", "bajada_ambicioso"]


def cargar_modelo():
    """Carga el modelo final, su lista de features y la mediana del año de train."""
    paquete_modelo = joblib.load(RUTA_MODELO)
    return paquete_modelo["modelo"], paquete_modelo["features"], paquete_modelo["mediana_anio_train"]


def preparar_hexagonos(mediana_anio_train):
    """Carga los hexágonos urbanos y rellena los nulos igual que en el entrenamiento."""
    hexagonos_todos = gpd.read_file(RUTA_HEXAGONOS)
    hexagonos = hexagonos_todos[hexagonos_todos["urbano"]].copy()
    hexagonos["plantas_media"] = hexagonos["plantas_media"].fillna(0)
    hexagonos["altura_arboles"] = hexagonos["altura_arboles"].fillna(0)
    hexagonos["anio_medio"] = hexagonos["anio_medio"].fillna(mediana_anio_train)
    return hexagonos


def asignar_hexagono(hexagonos):
    """Carga los centros de mayores y les asigna el hexágono en el que están."""
    centros = gpd.read_file(RUTA_CENTROS)
    centros = gpd.sjoin(centros, hexagonos[["h3", "geometry"]], how="left", predicate="within")
    return centros.drop(columns=["index_right"])


def calcular_limites(hexagonos):
    """Devuelve el aumento de NDVI por punto de copa y el NDVI máximo de la zona urbana."""
    relacion = LinearRegression()
    relacion.fit(hexagonos[["pct_copa"]], hexagonos["ndvi"])
    return relacion.coef_[0], hexagonos["ndvi"].max()


def simular_arbolado(tabla, aumento_copa, pendiente_ndvi, ndvi_maximo):
    """Devuelve una copia de la tabla con la copa y el NDVI aumentados según el escenario."""
    simulada = tabla.copy()
    copa_maxima = 100 - simulada["pct_edificado"]
    nueva_copa = np.minimum(simulada["pct_copa"] + aumento_copa, copa_maxima)
    aumento_real = np.maximum(nueva_copa - simulada["pct_copa"], 0)

    nuevo_ndvi = simulada["ndvi"] + pendiente_ndvi * aumento_real
    simulada["ndvi"] = np.maximum(simulada["ndvi"], np.minimum(nuevo_ndvi, ndvi_maximo))
    simulada["pct_copa"] = simulada["pct_copa"] + aumento_real
    return simulada


def simular_escenarios(hexagonos_centros, modelo, features, pendiente_ndvi, ndvi_maximo):
    """Predice la temperatura actual y la de cada escenario, y calcula la bajada."""
    hexagonos_centros = hexagonos_centros.copy()
    hexagonos_centros["lst_actual"] = modelo.predict(hexagonos_centros[features])
    for nombre, aumento in ESCENARIOS.items():
        simulada = simular_arbolado(hexagonos_centros, aumento, pendiente_ndvi, ndvi_maximo)
        hexagonos_centros[f"lst_{nombre}"] = modelo.predict(simulada[features])
        hexagonos_centros[f"bajada_{nombre}"] = hexagonos_centros["lst_actual"] - hexagonos_centros[f"lst_{nombre}"]
    return hexagonos_centros


def simular_centros():
    """Encadena todos los pasos y devuelve los centros con su temperatura actual y la bajada de cada escenario."""
    modelo, features, mediana_anio_train = cargar_modelo()
    hexagonos = preparar_hexagonos(mediana_anio_train)
    centros = asignar_hexagono(hexagonos)
    pendiente_ndvi, ndvi_maximo = calcular_limites(hexagonos)

    hexagonos_centros = hexagonos[hexagonos["h3"].isin(centros["h3"])]
    hexagonos_centros = simular_escenarios(hexagonos_centros, modelo, features, pendiente_ndvi, ndvi_maximo)
    return centros.merge(hexagonos_centros[["h3"] + COLUMNAS_RESULTADO], on="h3", how="left")