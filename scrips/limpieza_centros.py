"""Funciones de limpieza del registro de centros de atención social (Comunidad de Madrid)."""

import pandas as pd
import geopandas as gpd

from config import CRS_PROYECTO

TIPOS_GESTION_CENTRO = ["CENTROS RESIDENCIALES", "CENTROS DE DÍA"]

COLUMNAS_UTILES = {
    "numero_registro": "codigo",
    "denominacion": "nombre",
    "subtipo": "subtipo",
    "plazas_autorizadas_numero": "plazas",
    "direccion_distrito": "distrito",
    "direccion_coor_x": "x",
    "direccion_coor_y": "y",
    "entidad_denominacion": "entidad",
    "entidad_naturaleza": "titularidad",
    "tipo_gestion": "tipo_gestion"
}

TIPOS_CENTRO = {
    "RESIDENCIAS DE PERSONAS MAYORES DEPENDIENTES": "residencia",
    "RESIDENCIAS DE PERSONAS MAYORES MIXTA": "residencia",
    "RESIDENCIAS DE PERSONAS MAYORES AUTONOMAS": "residencia",
    "CENTROS DE DÍA: OTROS": "centro de día",
    "HOGARES Y CLUBES": "centro de mayores",
    "PISOS TUTELADOS": "vivienda tutelada",
    "CENTROS RESIDENCIALES: OTROS": "vivienda tutelada"
}


def cargar_registro(ruta):
    """Carga el CSV del registro de centros (separador punto y coma)."""
    return pd.read_csv(ruta, sep=";", encoding="utf-8")


def filtrar_centros(centros):
    """Deja los centros de Madrid capital, de personas mayores, residenciales o de día."""
    return centros[
        (centros["municipio_nombre"] == "Madrid") &
        (centros["sector"] == "Personas mayores") &
        (centros["tipo"].isin(TIPOS_GESTION_CENTRO))
    ]


def eliminar_sin_coordenadas(centros):
    """Convierte las coordenadas a número y elimina los centros sin ubicación."""
    centros = centros.copy()
    centros["direccion_coor_x"] = pd.to_numeric(centros["direccion_coor_x"], errors="coerce")
    centros["direccion_coor_y"] = pd.to_numeric(centros["direccion_coor_y"], errors="coerce")
    return centros.dropna(subset=["direccion_coor_x", "direccion_coor_y"])


def seleccionar_columnas(centros):
    """Deja solo las columnas útiles y acorta sus nombres."""
    return centros[list(COLUMNAS_UTILES.keys())].rename(columns=COLUMNAS_UTILES)


def clasificar_tipo(centros):
    """Crea la columna tipo_centro a partir del subtipo."""
    centros = centros.copy()
    centros["tipo_centro"] = centros["subtipo"].map(TIPOS_CENTRO)
    return centros


def crear_capa(centros):
    """Convierte la tabla en una capa de puntos en el sistema de coordenadas del proyecto."""
    centros = centros.reset_index(drop=True)
    return gpd.GeoDataFrame(
        centros,
        geometry=gpd.points_from_xy(centros["x"], centros["y"]),
        crs=CRS_PROYECTO
    )


def limpiar_centros(ruta):
    """Encadena todos los pasos de limpieza y devuelve la capa de centros limpia."""
    centros = cargar_registro(ruta)
    centros = filtrar_centros(centros)
    centros = eliminar_sin_coordenadas(centros)
    centros = seleccionar_columnas(centros)
    centros = clasificar_tipo(centros)
    return crear_capa(centros)