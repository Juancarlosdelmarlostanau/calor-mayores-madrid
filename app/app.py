"""App de Streamlit: calor y mayores en Madrid."""

import os

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

CARPETA_APP = os.path.dirname(os.path.abspath(__file__))
RUTA_CLEAN = os.path.join(CARPETA_APP, "..", "clean", "")
COLORES_PRIORIDAD = {"alta": "red", "media": "orange", "baja": "#ffe680"}
TEXTO_MEDIDA = {
    "vegetacion": "Plantar áboles",
    "suelo_desnudo": "Ajardinar solares y descampados",
    "edificios": "Tejados frescos (claros o verdes)",
    "parques": "Creacion de parque cercano",
    "ninguna": "Servicios(refugios, fuentes)"
}

st.set_page_config(page_title="Calor y mayores en Madrid", layout="wide")


@st.cache_data
def cargar_datos():
    """Lee una sola vez los resultados del proyecto guardados en clean/."""
    indice = gpd.read_file(RUTA_CLEAN + "indice_riesgo.gpkg")
    candidatos = gpd.read_file(RUTA_CLEAN + "priorizacion_hexagonos.gpkg")
    distritos = gpd.read_file(RUTA_CLEAN + "app_distritos.gpkg")
    antes_despues = pd.read_csv(RUTA_CLEAN + "priorizacion_centros.csv")
    curva = pd.read_csv(RUTA_CLEAN + "priorizacion_curva.csv")
    diagnostico = pd.read_csv(RUTA_CLEAN + "priorizacion_diagnostico.csv")

    indice = indice.merge(diagnostico[["codigo", "medida"]], on="codigo", how="left")
    indice["medida_texto"] = indice["medida"].map(TEXTO_MEDIDA)
    return indice, candidatos, distritos, antes_despues, curva


indice, candidatos, distritos, antes_despues, curva = cargar_datos()

st.title("Calor y mayores en Madrid")
st.write("En verano, Madrid no es igual de caliente para todos. Esta app muestra qué centros de mayores "
         "tienen el entorno de 15 minutos andando más caluroso y peor protegido, y dónde plantar árboles primero.")

tab_resumen, tab_ciudad, tab_centro = st.tabs(["Resumen", "La ciudad", "Un centro"])

with tab_resumen:
    n_alta = (indice["prioridad"] == "alta").sum()
    plan = antes_despues[antes_despues["plan_moderado"] > 0]
    n_alta_plan = (plan["prioridad"] == "alta").sum()
    veces_mejor = curva.loc[curva["hexagonos"] == 50, "veces_mejor"].iloc[0]
    bajada_fase3 = candidatos.loc[candidatos["elegido"], "plan_ambicioso"].mean()

    columna1, columna2, columna3, columna4 = st.columns(4)
    columna1.metric("Centros en prioridad alta", f"{n_alta} de {len(indice)}")
    columna2.metric("Prioritarios alcanzados por el plan", f"{n_alta_plan} de {n_alta}")
    columna3.metric("Mejor que elegir al azar", f"{veces_mejor:.1f} veces")
    columna4.metric("Bajada donde se planta (fase 3)", f"−{bajada_fase3:.2f} °C")

    filtro1, filtro2 = st.columns(2)
    tipos_elegidos = filtro1.multiselect("Tipo de centro", sorted(indice["tipo_centro"].unique()),
                                         default=sorted(indice["tipo_centro"].unique()))
    prioridades_elegidas = filtro2.multiselect("Prioridad", ["alta", "media", "baja"],
                                               default=["alta", "media", "baja"])
    filtrado = indice[indice["tipo_centro"].isin(tipos_elegidos) & indice["prioridad"].isin(prioridades_elegidas)]

    columna_mapa, columna_datos = st.columns([3, 2])

    with columna_mapa:
        st.markdown(
            '<span style="color:red">●</span> Prioridad alta &nbsp;&nbsp; '
            '<span style="color:orange">●</span> Prioridad media &nbsp;&nbsp; '
            '<span style="color:#e6c200">●</span> Prioridad baja &nbsp;&nbsp; '
            f"— {len(filtrado)} centros",
            unsafe_allow_html=True
        )
        mapa = folium.Map(
            location=[40.42, -3.70],
            zoom_start=11,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
            attr="Esri, World Light Gray Canvas"
        )
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            overlay=True
        ).add_to(mapa)

        distritos_wgs84 = distritos.to_crs(epsg=4326)
        folium.GeoJson(
            distritos_wgs84[["NOMBRE", "geometry"]],
            style_function=lambda elemento: {"color": "#666666", "weight": 1, "fillOpacity": 0},
            tooltip=folium.GeoJsonTooltip(fields=["NOMBRE"], aliases=["Distrito:"])
        ).add_to(mapa)

        limite_madrid = gpd.GeoDataFrame(geometry=[distritos_wgs84.union_all()], crs="EPSG:4326")
        folium.GeoJson(
            limite_madrid,
            style_function=lambda elemento: {"color": "#222222", "weight": 2.5, "fillOpacity": 0}
        ).add_to(mapa)
        for _, centro in filtrado.to_crs(epsg=4326).iterrows():
            ficha = (f"<b>{centro['nombre']}</b><br>"
                     f"Tipo: {centro['tipo_centro']}<br>"
                     f"Plazas: {int(centro['plazas'])}<br>"
                     f"Prioridad: {centro['prioridad']} (riesgo {centro['riesgo']:.2f})<br>"
                     f"Medida recomendada: {centro['medida_texto']}")
            folium.CircleMarker(
                location=[centro.geometry.y, centro.geometry.x],
                radius=4.5,
                color="dimgrey",
                weight=1,
                fill=True,
                fill_color=COLORES_PRIORIDAD[centro["prioridad"]],
                fill_opacity=0.9,
                tooltip=ficha
            ).add_to(mapa)
        st_folium(mapa, height=900, use_container_width=True, returned_objects=[])

    with columna_datos:
        st.subheader("Medida recomendada")
        st.bar_chart(filtrado["medida_texto"].value_counts(), horizontal=True, height=300)

        st.subheader("Centros con más riesgo")
        tabla = filtrado.nlargest(15, "riesgo")[["nombre", "tipo_centro", "prioridad", "riesgo", "medida_texto"]]
        tabla = tabla.rename(columns={"nombre": "Centro", "tipo_centro": "Tipo", "prioridad": "Prioridad",
                                      "riesgo": "Riesgo", "medida_texto": "Medida"})
        st.dataframe(tabla.round(2), hide_index=True, use_container_width=True, height=420)

with tab_ciudad:
    st.write("En construcción.")

with tab_centro:
    st.write("En construcción.")