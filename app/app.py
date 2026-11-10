"""App de Streamlit: calor y mayores en Madrid."""

import os

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import folium
import altair as alt
import branca.colormap as cm
import streamlit.components.v1 as components
from streamlit_folium import st_folium
from folium.plugins import DualMap

CARPETA_APP = os.path.dirname(os.path.abspath(__file__))
RUTA_CLEAN = os.path.join(CARPETA_APP, "..", "clean", "")
COLORES_PRIORIDAD = {"alta": "red", "media": "orange", "baja": "#ffe680"}
TEXTO_MEDIDA = {
    "vegetacion": "Plantar árboles",
    "suelo_desnudo": "Ajardinar solares y descampados",
    "edificios": "Tejados frescos (claros o verdes)",
    "parques": "Creación de parque cercano",
    "ninguna": "Servicios (refugios, fuentes)"
}

st.set_page_config(page_title="Calor y mayores en Madrid", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stWidgetLabel"] p {font-size: 18px;}
    div[role="radiogroup"] label p {font-size: 18px;}
    [data-testid="stMetricLabel"] p {font-size: 18px;}
    [data-testid="stCheckbox"] label p {font-size: 18px;}
    </style>
    """,
    unsafe_allow_html=True
)


@st.cache_data
def cargar_datos():
    """Lee una sola vez los resultados del proyecto guardados en clean/."""
    indice = gpd.read_file(RUTA_CLEAN + "indice_riesgo.gpkg")
    candidatos = gpd.read_file(RUTA_CLEAN + "priorizacion_hexagonos.gpkg")
    distritos = gpd.read_file(RUTA_CLEAN + "app_distritos.gpkg")
    antes_despues = pd.read_csv(RUTA_CLEAN + "priorizacion_centros.csv")
    curva = pd.read_csv(RUTA_CLEAN + "priorizacion_curva.csv")
    diagnostico = pd.read_csv(RUTA_CLEAN + "priorizacion_diagnostico.csv")
    centros_hexagonos = pd.read_csv(RUTA_CLEAN + "centros_hexagonos.csv")

    indice = indice.merge(diagnostico[["codigo", "medida"]], on="codigo", how="left")
    indice["medida_texto"] = indice["medida"].map(TEXTO_MEDIDA)
    indice["puesto"] = indice["riesgo"].rank(ascending=False, method="first").astype(int)
    indice = indice.merge(antes_despues[["codigo", "plan_moderado", "plan_ambicioso"]], on="codigo", how="left")
    return indice, candidatos, distritos, antes_despues, curva, centros_hexagonos


indice, candidatos, distritos, antes_despues, curva, centros_hexagonos = cargar_datos()

@st.cache_data
def cargar_hexagonos():
    """Lee una sola vez los hexágonos con su temperatura, su marca de zona urbana y su distrito."""
    hexagonos = gpd.read_file(RUTA_CLEAN + "hexagonos_h3.gpkg", columns=["h3", "urbano", "lst"])
    distritos = gpd.read_file(RUTA_CLEAN + "app_distritos.gpkg")
    centroides = gpd.GeoDataFrame(hexagonos[["h3"]], geometry=hexagonos.centroid, crs=hexagonos.crs)
    distrito_hexagono = gpd.sjoin_nearest(centroides, distritos[["NOMBRE", "geometry"]], how="left")
    distrito_hexagono = distrito_hexagono.drop_duplicates(subset="h3")
    return hexagonos.merge(distrito_hexagono[["h3", "NOMBRE"]].rename(columns={"NOMBRE": "distrito"}),
                           on="h3", how="left")


hexagonos = cargar_hexagonos()

def texto_distancia(servicio, distancia, texto_ninguno):
    """Devuelve el texto de la distancia andando a un servicio, o que no hay ninguno a menos de 1 km."""
    if pd.isna(distancia):
        return f"{servicio}: {texto_ninguno} a menos de 1 km"
    return f"{servicio} a {int(round(distancia))} m"


def crear_ficha(grupo):
    """Crea la ficha HTML de un punto del mapa: un bloque por centro y el entorno común una sola vez."""
    primero = grupo.iloc[0]
    ficha = '<div style="font-size:12px; line-height:1.45">'

    for _, centro in grupo.iterrows():
        if pd.isna(centro["plazas"]):
            texto_plazas = "Plazas: sin dato"
        elif centro["tipo_centro"] == "centro de mayores":
            texto_plazas = f"Socios o aforo: {int(centro['plazas'])}"
        else:
            texto_plazas = f"Plazas: {int(centro['plazas'])}"
        ficha += (f"<b>{centro['nombre']}</b><br>"
                  f"Tipo: {centro['tipo_centro']}<br>"
                  f"{texto_plazas}<br>"
                  f"Prioridad: {centro['prioridad']} (puesto {centro['puesto']} de {len(indice)})<br><br>")

    ficha += '<hr style="margin:4px 0"><b>Su entorno</b><br>'
    ficha += f"Caminable con comodidad: {primero['pct_confort_1.5']:.0f} % de sus 15 minutos andando<br>"
    ficha += texto_distancia("Fuente", primero["dist_agua"], "ninguna") + "<br>"
    ficha += texto_distancia("Refugio", primero["dist_refugio"], "ninguno") + "<br>"
    ficha += texto_distancia("Centro de salud", primero["dist_salud"], "ninguno") + "<br>"

    ficha += '<hr style="margin:4px 0"><b>Qué necesita su entorno</b><br>'
    ficha += f"{primero['medida_texto']}<br>"
    if primero["plan_moderado"] > 0:
        ficha += (f"Incluido en el plan de arbolado: su entorno se enfría "
                  f"−{primero['plan_ambicioso']:.2f} °C de media (fase +20 de copa)")
    elif primero["medida"] == "vegetacion":
        ficha += "Pendiente: no está entre las 50 zonas más urgentes del plan de arbolado"
    else:
        ficha += "El plan de arbolado no es su prioridad"
    return ficha + "</div>"

st.title("Calor y mayores en Madrid")
st.write("En verano, Madrid no es igual de caliente para todos. Esta app muestra qué centros de mayores "
         "tienen el entorno de 15 minutos andando más caluroso y peor protegido, y dónde plantar árboles primero.")

tab_resumen, tab_ciudad, tab_centro = st.tabs(["Resumen", "La ciudad", "Un centro"])

with tab_resumen:
    filtro1, filtro2 = st.columns(2)
    tipos_elegidos = filtro1.multiselect("Tipo de centro", sorted(indice["tipo_centro"].unique()),
                                         default=sorted(indice["tipo_centro"].unique()))
    prioridades_elegidas = filtro2.multiselect("Prioridad", ["alta", "media", "baja"],
                                               default=["alta", "media", "baja"])
    filtrado = indice[indice["tipo_centro"].isin(tipos_elegidos) & indice["prioridad"].isin(prioridades_elegidas)]
    plan_filtrado = antes_despues[antes_despues["codigo"].isin(filtrado["codigo"]) & (antes_despues["plan_moderado"] > 0)]

    with st.expander("¿Qué es el plan de arbolado?"):
        st.write("El plan: aumentar la sombra de árboles en 50 zonas de la ciudad, de unas 10 hectáreas cada una "
                 "(como 10 campos de fútbol). No se trata de llenarlas de árboles, sino de cubrir con copas entre "
                 "un 5 % y un 20 % más de su superficie, en calles, plazas y patios. El modelo elige las zonas donde "
                 "eso más enfría el entorno de los centros con más riesgo.")

    columna1, columna2, columna3, columna4 = st.columns(4)
    columna1.metric(
        "Centros seleccionados",
        f"{len(filtrado)} de {len(indice)}",
        help="Centros que cumplen los filtros de tipo y prioridad."
    )
    columna2.metric(
        "Se benefician de plantar árboles",
        f"{len(plan_filtrado)} de {len(filtrado)}",
        help="Centros que tienen, a menos de 15 minutos andando, alguna de las 50 zonas del plan de arbolado."
    )
    hexagonos_filtro = centros_hexagonos.loc[centros_hexagonos["codigo"].isin(filtrado["codigo"]), "h3"]
    zonas_plan_filtro = candidatos[candidatos["elegido"] & candidatos["h3"].isin(hexagonos_filtro)]

    ayuda_bajada = ("Bajada media de la temperatura del suelo en las zonas del plan de arbolado que están a menos de "
                    "15 minutos andando de estos centros, si se planta +20 % de copa. Debajo, la bajada media de todo "
                    "su entorno de 15 minutos, donde también hay zonas sin intervenir.")
    if len(zonas_plan_filtro) > 0:
        columna3.metric("Cuánto se enfría donde se planta", f"−{zonas_plan_filtro['plan_ambicioso'].mean():.2f} °C",
                        help=ayuda_bajada)
        columna3.caption(f"−{plan_filtrado['plan_ambicioso'].mean():.2f} °C de media en todo su entorno de 15 minutos")
    else:
        columna3.metric("Cuánto se enfría donde se planta", "—", help=ayuda_bajada)
    columna4.metric(
        "Sin refugio a 1 km andando",
        f"{filtrado['dist_refugio'].isnull().sum()} de {len(filtrado)}",
        help="Centros sin ningún refugio climático (centro de mayores o mercado) a menos de 1 km andando por la calle."
    )
    tabla_centros = filtrado.sort_values("puesto")[["codigo", "puesto", "nombre", "prioridad",
                                                    "pct_confort_1.5", "dist_refugio"]].reset_index(drop=True)
    tabla_centros["refugio_texto"] = tabla_centros["dist_refugio"].apply(
        lambda distancia: "ninguno" if pd.isna(distancia) else f"{int(round(distancia))} m")

    codigo_elegido = None
    estado_tabla = st.session_state.get("tabla_centros")
    if estado_tabla is not None:
        filas = estado_tabla["selection"]["rows"]
        if len(filas) > 0 and filas[0] < len(tabla_centros):
            codigo_elegido = tabla_centros.loc[filas[0], "codigo"]
    columna_mapa, columna_datos = st.columns([3, 2])

    with columna_mapa:
        conteo = filtrado["prioridad"].value_counts()
        st.markdown(
            f'<span style="color:red">●</span> Prioridad alta ({conteo.get("alta", 0)}) &nbsp;&nbsp; '
            f'<span style="color:orange">●</span> Prioridad media ({conteo.get("media", 0)}) &nbsp;&nbsp; '
            f'<span style="color:#e6c200">●</span> Prioridad baja ({conteo.get("baja", 0)})',
            unsafe_allow_html=True
        )
        filtrado_wgs84 = filtrado.to_crs(epsg=4326)
        filtrado_wgs84["lugar"] = filtrado.geometry.x.round().astype(str) + "_" + filtrado.geometry.y.round().astype(str)

        if codigo_elegido is not None:
            punto_elegido = filtrado_wgs84[filtrado_wgs84["codigo"] == codigo_elegido].geometry.iloc[0]
            centro_mapa, zoom_mapa = [punto_elegido.y, punto_elegido.x], 15
        else:
            centro_mapa, zoom_mapa = [40.42, -3.70], 11

        mapa = folium.Map(
            location=centro_mapa,
            zoom_start=zoom_mapa,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
            attr="Esri, World Topo Map"
        )

        distritos_wgs84 = distritos.to_crs(epsg=4326)
        limite_madrid = gpd.GeoDataFrame(geometry=[distritos_wgs84.union_all()], crs="EPSG:4326")
        folium.GeoJson(
            limite_madrid,
            style_function=lambda elemento: {"color": "#222222", "weight": 2.5, "fillOpacity": 0}
        ).add_to(mapa)

        for _, grupo in filtrado_wgs84.groupby("lugar"):
            grupo = grupo.sort_values("riesgo", ascending=False)
            primero = grupo.iloc[0]
            if len(grupo) > 1:
                texto_raton = f"{len(grupo)} centros: " + " / ".join(grupo["nombre"])
            else:
                texto_raton = primero["nombre"]

            elegido = codigo_elegido in grupo["codigo"].values
            folium.CircleMarker(
                location=[primero.geometry.y, primero.geometry.x],
                radius=10 if elegido else 4.5,
                color="#0b3d91" if elegido else "dimgrey",
                weight=3 if elegido else 1,
                fill=True,
                fill_color="#1f77b4" if elegido else COLORES_PRIORIDAD[primero["prioridad"]],
                fill_opacity=0.9,
                tooltip=texto_raton,
                popup=folium.Popup(crear_ficha(grupo), max_width=320, show=elegido)
            ).add_to(mapa)

        st_folium(mapa, height=900, use_container_width=True, returned_objects=[], key=f"mapa_{codigo_elegido}")

    with columna_datos:
        st.subheader("Qué necesita su entorno")
        datos_grafico = filtrado[["medida_texto", "plan_moderado"]].copy()
        datos_grafico["estado"] = (datos_grafico["plan_moderado"] > 0).map({True: "En el plan de arbolado",
                                                                            False: "Fuera del plan"})
        conteo_medidas = datos_grafico.groupby(["medida_texto", "estado"]).size().reset_index(name="centros")

        grafico = alt.Chart(conteo_medidas).mark_bar().encode(
            x=alt.X("centros:Q", title="Nº de centros"),
            y=alt.Y("medida_texto:N", sort="-x", title=None, axis=alt.Axis(labelLimit=250)),
            color=alt.Color("estado:N",
                            scale=alt.Scale(domain=["En el plan de arbolado", "Fuera del plan"],
                                            range=["#1f77b4", "#aec7e8"]),
                            legend=alt.Legend(title=None, orient="top")),
            order=alt.Order("estado:N"),
            tooltip=["medida_texto", "estado", "centros"]
        ).properties(height=300)
        st.altair_chart(grafico, use_container_width=True)

        st.subheader("Lista de centros")
        st.caption("Selecciona un centro para verlo en el mapa.")
        st.dataframe(
            tabla_centros[["puesto", "nombre", "prioridad", "pct_confort_1.5", "refugio_texto"]],
            key="tabla_centros",
            on_select="rerun",
            selection_mode="single-row",
            hide_index=True,
            use_container_width=True,
            height=465,
            column_config={
                "puesto": st.column_config.NumberColumn("Puesto", width="small",
                                                        help="1 = el centro con más riesgo de calor de Madrid"),
                "nombre": st.column_config.TextColumn("Centro", width="medium"),
                "prioridad": st.column_config.TextColumn("Prioridad", width="small"),
                "pct_confort_1.5": st.column_config.NumberColumn("Confort", width="small", format="%.0f%%",
                                                                 help="% de su entorno de 15 minutos que se puede caminar con comodidad"),
                "refugio_texto": st.column_config.TextColumn("Refugio", width="small",
                                                             help="Distancia andando al refugio climático más cercano (máximo 1 km)")
            }
        )

with tab_ciudad:
    st.subheader("¿Cuánto se puede enfriar la ciudad plantando árboles?")
    st.markdown(
        '<p style="font-size:18px">El mapa muestra la temperatura del suelo en verano por zonas. Elige una fase '
        'para ver cuánto bajaría si se plantaran árboles en el entorno de 15 minutos de todos los centros de '
        'mayores (potencial máximo).</p>',
        unsafe_allow_html=True
    )

    columna_izquierda, columna_derecha = st.columns(2)
    nombres_distritos = sorted(distritos["NOMBRE"].unique())
    distrito_elegido = columna_izquierda.selectbox("Distrito", ["Toda la ciudad"] + nombres_distritos)
    fases_ciudad = {
        "Fase 1 (+5 % de copa)": "bajada_bajo",
        "Fase 2 (+10 % de copa)": "bajada_moderado",
        "Fase 3 (+20 % de copa)": "bajada_ambicioso"
    }
    fase_elegida = columna_derecha.radio("Fase del mapa de la derecha", ["Hoy"] + list(fases_ciudad.keys()),
                                         horizontal=True)
    columna_bajada = fases_ciudad.get(fase_elegida)

    urbanos = hexagonos[hexagonos["urbano"]].copy()
    if columna_bajada is None:
        urbanos["bajada"] = 0.0
    else:
        urbanos = urbanos.merge(candidatos[["h3", columna_bajada]], on="h3", how="left")
        urbanos["bajada"] = urbanos[columna_bajada].fillna(0)
    urbanos["lst_fase"] = urbanos["lst"] - urbanos["bajada"]
    lst_minimo = urbanos["lst"].quantile(0.05)
    lst_maximo = urbanos["lst"].quantile(0.95)

    if distrito_elegido == "Toda la ciudad":
        zona = urbanos
    else:
        zona = urbanos[urbanos["distrito"] == distrito_elegido]
    entorno = zona["h3"].isin(candidatos["h3"])
    zonas_hoy = (zona["lst"] > 47).sum()
    zonas_fase = (zona["lst_fase"] > 47).sum()

    tarjeta1, tarjeta2, tarjeta3 = st.columns(3)
    ayuda1 = "Media de las zonas a menos de 15 minutos andando de algún centro de mayores."
    ayuda2 = "Zonas urbanas cuyo suelo supera los 47 °C, que hoy son la cuarta parte más caliente de Madrid."
    if columna_bajada is None:
        tarjeta1.metric("Temperatura media del entorno de los centros",
                        f"{zona.loc[entorno, 'lst'].mean():.1f} °C", help=ayuda1)
        tarjeta2.metric("Zonas muy calientes (más de 47 °C)", f"{zonas_hoy} de {len(zona)}", help=ayuda2)
        tarjeta3.metric("Zona más caliente hoy", f"{zona['lst'].max():.1f} °C",
                        help="La temperatura del suelo de la zona urbana más caliente.")
    else:
        tarjeta1.metric("Temperatura media del entorno de los centros",
                        f"{zona.loc[entorno, 'lst_fase'].mean():.1f} °C",
                        delta=f"{-zona.loc[entorno, 'bajada'].mean():.2f} °C", delta_color="inverse", help=ayuda1)
        tarjeta2.metric("Zonas muy calientes (más de 47 °C)", f"{zonas_fase} de {len(zona)}",
                        delta=f"{zonas_fase - zonas_hoy}", delta_color="inverse", help=ayuda2)
        tarjeta3.metric("Zona que más se enfría", f"−{zona['bajada'].max():.2f} °C",
                        help="La mayor bajada de temperatura del suelo en una sola zona con la fase elegida.")

    ver_centros = st.checkbox("Mostrar los centros de mayores")

    st.markdown(
        f'<div style="font-size:16px; margin-top:8px">Temperatura del suelo en verano</div>'
        f'<div style="display:flex; align-items:center; gap:10px; font-size:16px; margin-bottom:8px">'
        f'<span>{lst_minimo:.0f} °C o menos</span>'
        f'<div style="flex:1; height:14px; border-radius:3px; '
        f'background:linear-gradient(to right, #ffffcc, #fed976, #fd8d3c, #e31a1c, #800026)"></div>'
        f'<span>{lst_maximo:.0f} °C o más</span></div>',
        unsafe_allow_html=True
    )

    colores_calor = cm.linear.YlOrRd_09.scale(lst_minimo, lst_maximo)
    urbanos_wgs84 = urbanos.to_crs(epsg=4326)
    urbanos_wgs84["color_hoy"] = urbanos_wgs84["lst"].apply(colores_calor)
    urbanos_wgs84["color_fase"] = urbanos_wgs84["lst_fase"].apply(colores_calor)
    urbanos_wgs84["texto_hoy"] = "Hoy: " + urbanos_wgs84["lst"].round(1).astype(str) + " °C"
    urbanos_wgs84["texto_fase"] = (urbanos_wgs84["texto_hoy"] + " → " + fase_elegida + ": "
                                   + urbanos_wgs84["lst_fase"].round(1).astype(str) + " °C")

    distritos_wgs84 = distritos.to_crs(epsg=4326)
    if distrito_elegido == "Toda la ciudad":
        xmin, ymin, xmax, ymax = distritos_wgs84.total_bounds
        zoom_inicial = 11
    else:
        xmin, ymin, xmax, ymax = distritos_wgs84[distritos_wgs84["NOMBRE"] == distrito_elegido].total_bounds
        zoom_inicial = 13

    mapa_doble = DualMap(
        location=[(ymin + ymax) / 2, (xmin + xmax) / 2],
        zoom_start=zoom_inicial,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, World Topo Map"
    )

    folium.GeoJson(
        hexagonos[~hexagonos["urbano"]].to_crs(epsg=4326)[["geometry"]],
        style_function=lambda elemento: {"color": "none", "fillColor": "#e6e6e6", "fillOpacity": 0.6}
    ).add_to(mapa_doble)
    folium.GeoJson(
        urbanos_wgs84[["texto_hoy", "color_hoy", "geometry"]],
        style_function=lambda elemento: {"color": "none", "fillColor": elemento["properties"]["color_hoy"],
                                         "fillOpacity": 0.8},
        tooltip=folium.GeoJsonTooltip(fields=["texto_hoy"], labels=False)
    ).add_to(mapa_doble.m1)
    folium.GeoJson(
        urbanos_wgs84[["texto_fase", "color_fase", "geometry"]],
        style_function=lambda elemento: {"color": "none", "fillColor": elemento["properties"]["color_fase"],
                                         "fillOpacity": 0.8},
        tooltip=folium.GeoJsonTooltip(fields=["texto_fase"], labels=False)
    ).add_to(mapa_doble.m2)
    folium.GeoJson(
        distritos_wgs84[["NOMBRE", "geometry"]],
        style_function=lambda elemento: {"color": "#222222", "weight": 2.5, "fillOpacity": 0}
    ).add_to(mapa_doble)

    if distrito_elegido != "Toda la ciudad":
        folium.GeoJson(
            distritos_wgs84[distritos_wgs84["NOMBRE"] == distrito_elegido][["geometry"]],
            style_function=lambda elemento: {"color": "#1f77b4", "weight": 5, "fillOpacity": 0}
        ).add_to(mapa_doble)

    if ver_centros:
        for _, centro in indice.to_crs(epsg=4326).iterrows():
            folium.CircleMarker(
                location=[centro.geometry.y, centro.geometry.x],
                radius=2, color="black", weight=1, fill=True, fill_color="black", fill_opacity=1,
                tooltip=centro["nombre"]
            ).add_to(mapa_doble)

    components.html(mapa_doble.get_root().render(), height=650)

    st.subheader(distrito_elegido)
    datos_hoy = pd.DataFrame({"temperatura": zona["lst"], "momento": "Hoy"})
    if columna_bajada is None:
        datos_histograma = datos_hoy
        colores_momento = alt.Scale(domain=["Hoy"], range=["#9e9e9e"])
    else:
        datos_fase = pd.DataFrame({"temperatura": zona["lst_fase"], "momento": fase_elegida})
        datos_histograma = pd.concat([datos_hoy, datos_fase], ignore_index=True)
        colores_momento = alt.Scale(domain=["Hoy", fase_elegida], range=["#9e9e9e", "#fd8d3c"])

    barras = alt.Chart(datos_histograma).mark_bar(opacity=0.6).encode(
        x=alt.X("temperatura:Q", bin=alt.Bin(step=0.5), title="Temperatura del suelo en verano (°C)"),
        y=alt.Y("count()", stack=None, title="Nº de zonas"),
        color=alt.Color("momento:N", scale=colores_momento, legend=alt.Legend(title=None, orient="top"))
    )
    linea_47 = alt.Chart(pd.DataFrame({"umbral": [47]})).mark_rule(color="#e31a1c", strokeDash=[6, 4]).encode(
        x="umbral:Q"
    )
    st.altair_chart((barras + linea_47).properties(height=320), use_container_width=True)
    st.caption("La línea roja discontinua marca los 47 °C: a su derecha están las zonas muy calientes.")

with tab_centro:
    st.write("En construcción.")

st.divider()
st.markdown(":gray[Datos: Landsat 8 y 9 (veranos 2023-2026), Sentinel-2, Catastro, Urban Atlas 2021 (Copernicus), "
            "OpenStreetMap, Ayuntamiento de Madrid y Comunidad de Madrid (datos abiertos).]")
st.markdown(":gray[**Proyecto final de Ironhack Data Analytics** · Juan Carlos Del Mar Lostanau, 2026]")