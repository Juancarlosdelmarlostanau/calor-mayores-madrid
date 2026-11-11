"""App de Streamlit: calor y mayores en Madrid."""

import os

import geopandas as gpd
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

@st.cache_resource
def cargar_datos_centro():
    """Lee una sola vez las capas del mapa de un centro: calles, edificios, isócronas, servicios y diagnóstico."""
    tramos_app = gpd.read_parquet(RUTA_CLEAN + "app_tramos.parquet")
    edificios_app = gpd.read_parquet(RUTA_CLEAN + "app_edificios.parquet")
    isocronas_normales = gpd.read_file(RUTA_CLEAN + "isocronas_normales.gpkg")
    isocronas_confortables = gpd.read_file(RUTA_CLEAN + "isocronas_confortables.gpkg")
    isocronas_plan = gpd.read_file(RUTA_CLEAN + "isocronas_confortables_plan.gpkg")
    fuentes = gpd.read_file(RUTA_CLEAN + "servicios_fuentes.gpkg")
    salud = gpd.read_file(RUTA_CLEAN + "servicios_salud.gpkg")
    refugios = gpd.read_file(RUTA_CLEAN + "servicios_refugios.gpkg")
    diagnostico = pd.read_csv(RUTA_CLEAN + "priorizacion_diagnostico.csv")
    return (tramos_app, edificios_app, isocronas_normales, isocronas_confortables, isocronas_plan,
            fuentes, salud, refugios, diagnostico)


(tramos_app, edificios_app, isocronas_normales, isocronas_confortables, isocronas_plan,
 fuentes_app, salud_app, refugios_app, diagnostico_app) = cargar_datos_centro()

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
    ZOOM_CIUDAD = 11
    ZOOM_DISTRITO = 13
    UMBRAL_ENTORNO = 45
    TAMANO_TRAMO = 0.25
    OPACIDAD_ENTORNO = 1
    OPACIDAD_FUERA = 1

    st.subheader("¿Cuánto se puede enfriar la ciudad plantando árboles?")
    st.markdown(
        '<p style="font-size:18px">El mapa de la izquierda muestra la temperatura del suelo en verano, hoy. '
        'El de la derecha, cuánto bajaría si se plantaran árboles en el entorno de 15 minutos andando de todos los '
        'centros de mayores (potencial máximo), según la fase elegida. Los dos usan los mismos colores, por tramos de '
        f'{TAMANO_TRAMO:.2f} °C'.replace(".", ",") + ': una zona que cambia de color ha bajado al menos de tramo. '
        '</p>',
        unsafe_allow_html=True
    )

    centros_distritos = gpd.sjoin(
        indice[["codigo", "nombre", "lst_isocrona", "prioridad", "puesto", "pct_confort_1.5", "geometry"]],
        distritos[["NOMBRE", "geometry"]], how="left", predicate="within"
    )
    fases_ciudad = {
        "Fase 1 (+5 % de copa)": "bajada_bajo",
        "Fase 2 (+10 % de copa)": "bajada_moderado",
        "Fase 3 (+20 % de copa)": "bajada_ambicioso"
    }

    with st.container(border=True):
        control1, control2 = st.columns(2)
        distrito_elegido = control1.selectbox("Distrito", ["Toda la ciudad"] + sorted(distritos["NOMBRE"].unique()))
        if distrito_elegido == "Toda la ciudad":
            centros_zona = centros_distritos.copy()
        else:
            centros_zona = centros_distritos[centros_distritos["NOMBRE"] == distrito_elegido].copy()
        centro_elegido = control2.selectbox("Ver un centro (mapa e histograma)",
                                            ["Ninguno"] + sorted(centros_zona["nombre"].unique()))
        control3, control4 = st.columns(2)
        fase_elegida = control3.radio("Fase del mapa de la derecha", list(fases_ciudad.keys()),
                                      index=2, horizontal=True)
        ver_centros = control4.checkbox("Mostrar los centros de mayores")
    columna_bajada = fases_ciudad[fase_elegida]
    nombre_fase = fase_elegida.split(" (")[0].lower()

    urbanos = hexagonos[hexagonos["urbano"]].copy()
    urbanos = urbanos.merge(candidatos[["h3", columna_bajada]], on="h3", how="left")
    urbanos["bajada"] = urbanos[columna_bajada].fillna(0)
    urbanos["lst_fase"] = urbanos["lst"] - urbanos["bajada"]
    urbanos["en_entorno"] = urbanos["h3"].isin(candidatos["h3"])
    lst_minimo = urbanos["lst"].quantile(0.05)
    lst_maximo = urbanos["lst"].quantile(0.95)

    if distrito_elegido == "Toda la ciudad":
        zona = urbanos
    else:
        zona = urbanos[urbanos["distrito"] == distrito_elegido]
    entorno = zona["en_entorno"]

    centros_zona = centros_zona.merge(antes_despues[["codigo", columna_bajada]], on="codigo", how="left")
    centros_zona["temperatura"] = centros_zona["lst_isocrona"] - centros_zona[columna_bajada]
    centros_zona["texto"] = ("Entorno hoy: " + centros_zona["lst_isocrona"].round(1).astype(str) + " °C → "
                             + centros_zona["temperatura"].round(1).astype(str) + " °C")

    st.markdown(f"#### {distrito_elegido}")
    tarjeta1, tarjeta2, tarjeta3, tarjeta4 = st.columns(4)
    tarjeta1.metric("Centros de mayores", f"{len(centros_zona)}",
                    help="Residencias, centros de día, centros de mayores y viviendas tuteladas en esta zona.")
    tarjeta1.caption(f"{(centros_zona['prioridad'] == 'alta').sum()} de prioridad alta")
    tarjeta2.metric("Temperatura media del entorno de los centros",
                    f"{zona.loc[entorno, 'lst_fase'].mean():.1f} °C",
                    delta=f"{-zona.loc[entorno, 'bajada'].mean():.2f} °C", delta_color="inverse",
                    help="Media de las zonas a menos de 15 minutos andando de algún centro de mayores, con la fase elegida.")
    centros_calientes_hoy = (centros_zona["lst_isocrona"] > UMBRAL_ENTORNO).sum()
    centros_calientes_fase = (centros_zona["temperatura"] > UMBRAL_ENTORNO).sum()
    tarjeta3.metric(f"Centros con el entorno por encima de {UMBRAL_ENTORNO} °C",
                    f"{centros_calientes_fase} de {len(centros_zona)}",
                    delta=f"{centros_calientes_fase - centros_calientes_hoy}", delta_color="inverse",
                    help=f"Centros cuyo entorno de 15 minutos supera de media los {UMBRAL_ENTORNO} °C, que hoy son "
                         "aproximadamente la cuarta parte más calurosa. La flecha indica cuántos salen de esa situación.")
    zonas_hoy = (zona["lst"] > 47).sum()
    zonas_fase = (zona["lst_fase"] > 47).sum()
    tarjeta4.metric("Zonas muy calientes (más de 47 °C)", f"{zonas_fase} de {len(zona)}",
                    delta=f"{zonas_fase - zonas_hoy}", delta_color="inverse",
                    help="Zonas urbanas cuyo suelo supera los 47 °C, que hoy son la cuarta parte más caliente de Madrid.")

    if centro_elegido != "Ninguno":
        fila_elegido = centros_zona[centros_zona["nombre"] == centro_elegido].iloc[0]
        with st.container(border=True):
            st.markdown(f'<p style="font-size:18px; color:#1f77b4"><b>▲ {centro_elegido}</b></p>',
                        unsafe_allow_html=True)
            ficha1, ficha2, ficha3, ficha4 = st.columns(4)
            ficha1.metric("Prioridad", f"{fila_elegido['prioridad']}",
                          help="Según el índice de riesgo de calor de los 439 centros.")
            ficha1.caption(f"puesto {fila_elegido['puesto']} de {len(indice)}")
            ficha2.metric("Su entorno hoy", f"{fila_elegido['lst_isocrona']:.1f} °C",
                          help="Temperatura media del suelo en sus 15 minutos andando.")
            ficha3.metric(f"Su entorno con la {nombre_fase}", f"{fila_elegido['temperatura']:.1f} °C",
                          delta=f"{fila_elegido['temperatura'] - fila_elegido['lst_isocrona']:.2f} °C",
                          delta_color="inverse")
            ficha4.metric("Caminable con comodidad", f"{fila_elegido['pct_confort_1.5']:.0f} %",
                          help="Parte de su entorno de 15 minutos que se puede recorrer sin exceso de calor, hoy.")

    pasos_por_grado = int(1 / TAMANO_TRAMO)
    tramos = [valor / pasos_por_grado
              for valor in range(int(lst_minimo) * pasos_por_grado, int(lst_maximo) * pasos_por_grado + 1)]
    colores_calor = cm.linear.YlOrRd_09.scale(tramos[0], tramos[-1]).to_step(index=tramos)

    bloques = ""
    for inicio in tramos[:-1]:
        if inicio == int(inicio):
            etiqueta = f"{int(inicio)}"
        else:
            etiqueta = ""
        bloques += (f'<div style="flex:1; text-align:left">'
                    f'<div style="height:14px; background:{colores_calor(inicio + TAMANO_TRAMO / 2)}"></div>'
                    f'<div style="font-size:13px">{etiqueta}</div></div>')
    st.markdown(
        f'<div style="font-size:16px; margin-top:8px">Temperatura del suelo en verano (°C). El primer tramo incluye '
                f'las zonas por debajo de {tramos[0]:.0f} °C y el último, las de más de {tramos[-1]:.0f} °C.</div>'
        f'<div style="display:flex; gap:1px; margin:4px 0 8px 0">{bloques}</div>',
        unsafe_allow_html=True
    )
    titulo_izquierdo, titulo_derecho = st.columns(2)
    titulo_izquierdo.markdown('<p style="font-size:18px; text-align:center"><b>Hoy</b></p>', unsafe_allow_html=True)
    titulo_derecho.markdown(f'<p style="font-size:18px; text-align:center"><b>{fase_elegida}</b></p>',
                            unsafe_allow_html=True)

    urbanos_wgs84 = urbanos.to_crs(epsg=4326)
    urbanos_wgs84["color_hoy"] = urbanos_wgs84["lst"].apply(colores_calor)
    urbanos_wgs84["color_fase"] = urbanos_wgs84["lst_fase"].apply(colores_calor)
    urbanos_wgs84["opacidad"] = urbanos_wgs84["en_entorno"].map({True: OPACIDAD_ENTORNO, False: OPACIDAD_FUERA})
    urbanos_wgs84["texto_hoy"] = "Hoy: " + urbanos_wgs84["lst"].round(1).astype(str) + " °C"
    urbanos_wgs84["texto_fase"] = (urbanos_wgs84["texto_hoy"] + " → " + fase_elegida + ": "
                                   + urbanos_wgs84["lst_fase"].round(1).astype(str) + " °C (baja "
                                   + urbanos_wgs84["bajada"].round(2).astype(str) + " °C)")
    urbanos_wgs84.loc[~urbanos_wgs84["en_entorno"], "texto_fase"] = (
        urbanos_wgs84["texto_hoy"] + " · fuera del entorno de los centros: no se planta")

    distritos_wgs84 = distritos.to_crs(epsg=4326)
    if distrito_elegido == "Toda la ciudad":
        xmin, ymin, xmax, ymax = distritos_wgs84.total_bounds
        zoom_inicial = ZOOM_CIUDAD
    else:
        xmin, ymin, xmax, ymax = distritos_wgs84[distritos_wgs84["NOMBRE"] == distrito_elegido].total_bounds
        zoom_inicial = ZOOM_DISTRITO

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
        urbanos_wgs84[["texto_hoy", "color_hoy", "opacidad", "geometry"]],
        style_function=lambda elemento: {"color": "none", "fillColor": elemento["properties"]["color_hoy"],
                                         "fillOpacity": elemento["properties"]["opacidad"]},
        tooltip=folium.GeoJsonTooltip(fields=["texto_hoy"], labels=False)
    ).add_to(mapa_doble.m1)
    folium.GeoJson(
        urbanos_wgs84[["texto_fase", "color_fase", "opacidad", "geometry"]],
        style_function=lambda elemento: {"color": "none", "fillColor": elemento["properties"]["color_fase"],
                                         "fillOpacity": elemento["properties"]["opacidad"]},
        tooltip=folium.GeoJsonTooltip(fields=["texto_fase"], labels=False)
    ).add_to(mapa_doble.m2)
    folium.GeoJson(
        distritos_wgs84[["NOMBRE", "geometry"]],
        style_function=lambda elemento: {"color": "#222222", "weight": 1.25, "fillOpacity": 0}
    ).add_to(mapa_doble)
    limite_madrid = gpd.GeoDataFrame(geometry=[distritos_wgs84.union_all()], crs="EPSG:4326")
    folium.GeoJson(
        limite_madrid,
        style_function=lambda elemento: {"color": "#222222", "weight": 2.5, "fillOpacity": 0}
    ).add_to(mapa_doble)
    if distrito_elegido != "Toda la ciudad":
        folium.GeoJson(
            distritos_wgs84[distritos_wgs84["NOMBRE"] == distrito_elegido][["geometry"]],
            style_function=lambda elemento: {"color": "#1f77b4", "weight": 5, "fillOpacity": 0}
        ).add_to(mapa_doble)
    if ver_centros:
        for _, centro in centros_zona.to_crs(epsg=4326).iterrows():
            folium.CircleMarker(
                location=[centro.geometry.y, centro.geometry.x],
                radius=2, color="black", weight=1, fill=True, fill_color="black", fill_opacity=1,
                tooltip=centro["nombre"]
            ).add_to(mapa_doble)
    if centro_elegido != "Ninguno":
        punto_elegido = centros_zona[centros_zona["nombre"] == centro_elegido].to_crs(epsg=4326).geometry.iloc[0]
        folium.CircleMarker(
            location=[punto_elegido.y, punto_elegido.x],
            radius=8, color="white", weight=2, fill=True, fill_color="#1f77b4", fill_opacity=1,
            tooltip=centro_elegido
        ).add_to(mapa_doble)
    components.html(mapa_doble.get_root().render(), height=650)

    st.subheader(f"Distribución de la temperatura de las zonas: {distrito_elegido}")
    st.markdown('<span style="color:#bdbdbd; font-size:16px">□ Hoy (silueta)</span> &nbsp;&nbsp; '
                f'<span style="color:#fd8d3c; font-size:16px">■ {fase_elegida}</span> &nbsp;&nbsp; '
                '<span style="font-size:16px">▲ Centros de mayores (temperatura media de su entorno)</span>',
                unsafe_allow_html=True)
    barras_fase = alt.Chart(pd.DataFrame({"temperatura": zona["lst_fase"]})).mark_bar(
        color="#fd8d3c", opacity=0.85).encode(
        x=alt.X("temperatura:Q", bin=alt.Bin(step=0.5), title="Temperatura del suelo en verano (°C)"),
        y=alt.Y("count()", title="Nº de zonas")
    )
    barras_hoy = alt.Chart(pd.DataFrame({"temperatura": zona["lst"]})).mark_bar(
        fillOpacity=0, stroke="#bdbdbd", strokeWidth=1.5).encode(
        x=alt.X("temperatura:Q", bin=alt.Bin(step=0.5)),
        y=alt.Y("count()")
    )
    umbral = pd.DataFrame({"umbral": [47], "etiqueta": ["47 °C · zona muy caliente"]})
    linea_47 = alt.Chart(umbral).mark_rule(color="#ff4b4b", strokeWidth=2, strokeDash=[6, 4]).encode(x="umbral:Q")
    texto_47 = alt.Chart(umbral).mark_text(color="#ff4b4b", align="left", dx=6, fontSize=13).encode(
        x="umbral:Q", y=alt.value(12), text="etiqueta:N"
    )
    grafico_histograma = barras_fase + barras_hoy + linea_47 + texto_47
    if distrito_elegido != "Toda la ciudad":
        triangulos = alt.Chart(centros_zona[["nombre", "temperatura", "texto"]]).mark_point(
            shape="triangle-up", filled=True, color="white", stroke="black", size=90, opacity=1, yOffset=-8).encode(
            x="temperatura:Q", y=alt.datum(0),
            tooltip=[alt.Tooltip("nombre:N", title="Centro"), alt.Tooltip("texto:N", title="Temperatura")]
        )
        grafico_histograma = grafico_histograma + triangulos
    if centro_elegido != "Ninguno":
        triangulo_elegido = alt.Chart(centros_zona[centros_zona["nombre"] == centro_elegido][
            ["nombre", "temperatura", "texto"]]).mark_point(
            shape="triangle-up", filled=True, color="#1f77b4", stroke="white", size=300, opacity=1, yOffset=-12).encode(
            x="temperatura:Q", y=alt.datum(0),
            tooltip=[alt.Tooltip("nombre:N", title="Centro"), alt.Tooltip("texto:N", title="Temperatura")]
        )
        grafico_histograma = grafico_histograma + triangulo_elegido
    st.altair_chart(grafico_histograma.properties(height=340), use_container_width=True)

    st.subheader("¿Dónde rinde más plantar?")
    por_distrito = centros_distritos.dropna(subset=["NOMBRE"]).merge(
        antes_despues[["codigo", columna_bajada]], on="codigo", how="left")
    por_distrito["fase"] = por_distrito["lst_isocrona"] - por_distrito[columna_bajada]
    resumen_distritos = por_distrito.groupby("NOMBRE").agg(
        hoy=("lst_isocrona", "mean"),
        fase=("fase", "mean"),
        centros=("codigo", "size")
    ).reset_index().rename(columns={"NOMBRE": "distrito"})
    resumen_distritos["bajada"] = resumen_distritos["hoy"] - resumen_distritos["fase"]
    resumen_distritos["elegido"] = resumen_distritos["distrito"] == distrito_elegido
    for columna in ["hoy", "fase", "bajada"]:
        resumen_distritos[columna] = resumen_distritos[columna].round(2)
    orden_distritos = resumen_distritos.sort_values("hoy", ascending=False)["distrito"].tolist()

    st.markdown('<p style="font-size:17px">Temperatura media del entorno de los centros de cada distrito: '
                '<span style="color:#9e9e9e"><b>● hoy</b></span> y '
                f'<span style="color:#fd8d3c"><b>● {fase_elegida.lower()}</b></span>. '
                'Ordenados del entorno más caliente hoy al menos caliente.</p>', unsafe_allow_html=True)
    eje_distrito = alt.Y("distrito:N", sort=orden_distritos, title=None, axis=alt.Axis(labelLimit=200))
    ayuda_distrito = [alt.Tooltip("distrito:N", title="Distrito"), alt.Tooltip("centros:Q", title="Centros"),
                      alt.Tooltip("hoy:Q", title="Hoy (°C)"), alt.Tooltip("fase:Q", title="Fase (°C)"),
                      alt.Tooltip("bajada:Q", title="Bajada (°C)")]
    lineas = alt.Chart(resumen_distritos).mark_rule().encode(
        x="fase:Q", x2="hoy:Q", y=eje_distrito,
        color=alt.condition(alt.datum.elegido, alt.value("#1f77b4"), alt.value("#bdbdbd")),
        strokeWidth=alt.condition(alt.datum.elegido, alt.value(4), alt.value(2))
    )
    puntos_hoy = alt.Chart(resumen_distritos).mark_circle(size=110, color="#9e9e9e", opacity=1).encode(
        x=alt.X("hoy:Q", scale=alt.Scale(zero=False), title="Temperatura media del entorno de los centros (°C)"),
        y=eje_distrito, tooltip=ayuda_distrito
    )
    puntos_fase = alt.Chart(resumen_distritos).mark_circle(size=110, color="#fd8d3c", opacity=1).encode(
        x="fase:Q", y=eje_distrito, tooltip=ayuda_distrito
    )
    umbral_entorno = pd.DataFrame({"umbral": [UMBRAL_ENTORNO],
                                   "etiqueta": [f"{UMBRAL_ENTORNO} °C · entorno muy caluroso"]})
    linea_45 = alt.Chart(umbral_entorno).mark_rule(color="#ff4b4b", strokeWidth=2, strokeDash=[6, 4]).encode(
        x="umbral:Q"
    )
    texto_45 = alt.Chart(umbral_entorno).mark_text(color="#ff4b4b", align="left", dx=6, fontSize=13).encode(
        x="umbral:Q", y=alt.value(-8), text="etiqueta:N"
    )
    st.altair_chart((lineas + puntos_hoy + puntos_fase + linea_45 + texto_45).properties(height=520),
                    use_container_width=True)

    entorno_ciudad = urbanos["en_entorno"]
    bajada_ciudad = urbanos.loc[entorno_ciudad, "bajada"].mean()
    zonas_menos = (urbanos["lst"] > 47).sum() - (urbanos["lst_fase"] > 47).sum()
    mas_ganan = ", ".join(resumen_distritos.nlargest(3, "bajada")["distrito"])
    mas_calientes = ", ".join(resumen_distritos.nlargest(3, "fase")["distrito"])
    st.info(f"**Conclusión:** con la {nombre_fase} en el entorno de todos los centros, la temperatura media del suelo "
            f"de ese entorno bajaría {bajada_ciudad:.2f} °C y {zonas_menos} zonas dejarían de superar los 47 °C. "
            f"Los distritos que más ganan son {mas_ganan}. Aun así, los entornos más calientes seguirían siendo los "
            f"de {mas_calientes}: ahí harán falta además otras medidas, como refugios y fuentes.")

    
with tab_centro:
    RADIO_ZOOM = 820
    ZOOM_CENTRO = 16
    ALTURA_MAPA = 720
    OPACIDAD_CALLES = 0.55
    PASOS_CENTRO = {
        "Hoy": "hoy",
        "Fase 1 (+5 % de copa)": "bajo",
        "Fase 2 (+10 % de copa)": "moderado",
        "Fase 3 (+20 % de copa)": "ambicioso"
    }
    TEXTO_PALANCA = {
        "vegetacion": ("Poca vegetación", "Mucha vegetación", "Vegetación"),
        "suelo_desnudo": ("Mucho suelo desnudo", "Poco suelo desnudo", "Suelo desnudo"),
        "edificios": ("Edificios bajos o naves al sol", "Edificios que dan sombra", "Edificios"),
        "parques": ("Lejos de un parque grande", "Cerca de un parque grande", "Distancia a un parque grande")
    }
    COLOR_FUENTE = "#1c83e1"
    COLOR_REFUGIO = "#21c354"
    COLOR_SALUD = "#803df5"
    COLOR_CENTRO = "#1f77b4"
    COLOR_COMODO = "#238b45"
    COLOR_LIMITE = "#00441b"

    def limpiar_direccion(texto):
        """Devuelve la dirección con las preposiciones en minúscula, o un texto vacío si no hay dirección."""
        if pd.isna(texto) or texto == "":
            return ""
        return str(texto).replace(" De ", " de ").replace(" Del ", " del ").replace(" La ", " la ")

    def texto_servicio(servicio, distancia, nombre, direccion, mostrar_nombre):
        """Devuelve la línea de un servicio: distancia andando, nombre y dirección del más cercano."""
        if pd.isna(distancia):
            return f"<b>{servicio}</b>: no hay ninguno a menos de 1 km andando"
        partes = [f"<b>{servicio}</b> a {int(round(distancia))} m andando"]
        if mostrar_nombre and not pd.isna(nombre):
            partes.append(str(nombre))
        if limpiar_direccion(direccion) != "":
            partes.append(limpiar_direccion(direccion))
        return " · ".join(partes)

    st.subheader("Un centro y su entorno de 15 minutos andando")
    st.markdown(
        '<p style="font-size:18px">Elige un centro para ver qué consigue el plan de arbolado realista (las 50 zonas '
        'elegidas por el modelo) en las calles por las que caminan sus usuarios, y por qué está en riesgo hoy.</p>',
        unsafe_allow_html=True
    )

    centros_ordenados = indice.sort_values("puesto")
    etiquetas_centros = dict(zip(centros_ordenados["codigo"],
                                 centros_ordenados["puesto"].astype(str) + ". " + centros_ordenados["nombre"]))
    with st.container(border=True):
        codigo_centro = st.selectbox("Centro (ordenados de más a menos riesgo; puedes escribir para buscar)",
                                     list(etiquetas_centros.keys()),
                                     format_func=lambda codigo: etiquetas_centros[codigo])

    fila = indice[indice["codigo"] == codigo_centro].iloc[0]
    fila_plan = antes_despues[antes_despues["codigo"] == codigo_centro].iloc[0]
    fila_diagnostico = diagnostico_app[diagnostico_app["codigo"] == codigo_centro].iloc[0]
    en_plan = fila_plan["plan_moderado"] > 0

    if en_plan:
        paso_elegido = st.select_slider("Evolución con el plan de arbolado: desliza para ver cada fase",
                                        options=list(PASOS_CENTRO.keys()), value="Hoy")
        st.markdown(
            '<div style="display:flex; justify-content:space-between; font-size:14px; color:#9e9e9e; '
            'margin-top:-12px; margin-bottom:8px"><span>Hoy</span><span>Fase 1 (+5 %)</span>'
            '<span>Fase 2 (+10 %)</span><span>Fase 3 (+20 %)</span></div>',
            unsafe_allow_html=True
        )
    else:
        paso_elegido = "Hoy"
        st.info("El plan de arbolado (50 zonas) no interviene en el entorno de este centro: se muestra la situación de hoy.")
    fase = PASOS_CENTRO[paso_elegido]

    temperatura_hoy = fila["lst_isocrona"]
    confort_hoy = fila["pct_confort_1.5"]
    if en_plan:
        evolucion = []
        for nombre_paso, clave in PASOS_CENTRO.items():
            if clave == "hoy":
                bajada = 0
            else:
                bajada = fila_plan[f"plan_{clave}"]
            confort_de_paso = isocronas_plan[(isocronas_plan["codigo"] == codigo_centro) &
                                             (isocronas_plan["fase"] == clave)]["pct_confort"].iloc[0]
            evolucion.append({"paso": nombre_paso.split(" (")[0],
                              "temperatura": round(temperatura_hoy - bajada, 2),
                              "confort": confort_de_paso})
        evolucion = pd.DataFrame(evolucion)
        fila_paso = evolucion[evolucion["paso"] == paso_elegido.split(" (")[0]].iloc[0]
        temperatura_paso = fila_paso["temperatura"]
        confort_paso = fila_paso["confort"]
    else:
        temperatura_paso = temperatura_hoy
        confort_paso = confort_hoy

    tarjeta1, tarjeta2, tarjeta3, tarjeta4 = st.columns(4)
    if pd.isna(fila["plazas"]):
        texto_plazas = "sin dato"
    elif fila["tipo_centro"] == "centro de mayores":
        texto_plazas = f"{int(fila['plazas'])} socios"
    else:
        texto_plazas = f"{int(fila['plazas'])} plazas"
    tarjeta1.metric("Quién está aquí", texto_plazas,
                    help="En los centros de mayores, la cifra son socios o aforo, no plazas asistenciales.")
    tarjeta1.caption(fila["tipo_centro"].capitalize())
    if fase == "hoy":
        tarjeta2.metric("Temperatura de su entorno", f"{temperatura_paso:.1f} °C",
                        help="Temperatura media del suelo en sus 15 minutos andando.")
        tarjeta3.metric("Caminable con comodidad", f"{confort_paso:.0f} %",
                        help="Parte de su entorno de 15 minutos que se puede recorrer sin exceso de calor.")
    else:
        tarjeta2.metric("Temperatura de su entorno", f"{temperatura_paso:.1f} °C",
                        delta=f"{temperatura_paso - temperatura_hoy:.2f} °C", delta_color="inverse",
                        help="Temperatura media del suelo en sus 15 minutos andando.")
        tarjeta3.metric("Caminable con comodidad", f"{confort_paso:.0f} %",
                        delta=f"{confort_paso - confort_hoy:+.1f} puntos",
                        help="Parte de su entorno de 15 minutos que se puede recorrer sin exceso de calor.")
    tarjeta4.metric("Sombra de árboles en su entorno", f"{fila['copa_isocrona']:.0f} %",
                    help="Parte del suelo de su entorno cubierta por copas de árboles, hoy.")
    tarjeta4.caption(f"media de los centros: {indice['copa_isocrona'].mean():.0f} %")

    columna_mapa, columna_derecha = st.columns([3, 2])

    with columna_mapa:
        x_centro, y_centro = fila.geometry.x, fila.geometry.y
        xmin, xmax = x_centro - RADIO_ZOOM, x_centro + RADIO_ZOOM
        ymin, ymax = y_centro - RADIO_ZOOM, y_centro + RADIO_ZOOM

        urbanos_lst = hexagonos.loc[hexagonos["urbano"], "lst"]
        escala_calles = cm.linear.YlOrRd_09.scale(urbanos_lst.quantile(0.05), urbanos_lst.quantile(0.95))

        isocrona_normal = isocronas_normales[isocronas_normales["codigo"] == codigo_centro]
        if en_plan:
            isocrona_comoda = isocronas_plan[(isocronas_plan["codigo"] == codigo_centro) &
                                             (isocronas_plan["fase"] == fase)]
        else:
            isocrona_comoda = isocronas_confortables[isocronas_confortables["codigo"] == codigo_centro]

        tramos_zona = tramos_app.cx[xmin:xmax, ymin:ymax]
        tramos_zona = tramos_zona[tramos_zona.intersects(isocrona_normal.geometry.iloc[0])].copy()
        if fase == "hoy":
            tramos_zona["lst_paso"] = tramos_zona["lst"]
        else:
            tramos_zona["lst_paso"] = tramos_zona["lst"] - tramos_zona[f"plan_{fase}"]
        tramos_zona["color"] = tramos_zona["lst_paso"].apply(escala_calles)
        tramos_zona["texto"] = "Calle: " + tramos_zona["lst_paso"].round(1).astype(str) + " °C"

        st.markdown(
            f'<div style="display:flex; align-items:center; gap:8px; font-size:15px">'
            f'<span>Calles: {urbanos_lst.quantile(0.05):.0f} °C</span>'
            f'<div style="flex:1; height:10px; border-radius:3px; opacity:{OPACIDAD_CALLES + 0.2}; '
            f'background:linear-gradient(to right, #ffffcc, #fed976, #fd8d3c, #e31a1c, #800026)"></div>'
            f'<span>{urbanos_lst.quantile(0.95):.0f} °C</span></div>'
            f'<div style="font-size:15px; margin:4px 0 4px 0">'
            f'<span style="color:{COLOR_LIMITE}"><b>- - -</b></span> 15 minutos andando &nbsp; '
            f'<span style="color:{COLOR_COMODO}">■</span> recorrido cómodo &nbsp; '
            f'<span style="color:#b0b0b0">■</span> edificios &nbsp; '
            f'<span style="color:{COLOR_CENTRO}">●</span> centro</div>',
            unsafe_allow_html=True
        )
        casilla_fuentes, casilla_refugios, casilla_salud, casilla_otros = st.columns(4)
        ver_fuentes = casilla_fuentes.checkbox(":blue[●] Fuentes")
        ver_refugios = casilla_refugios.checkbox(":green[●] Refugios")
        ver_salud = casilla_salud.checkbox(":violet[●] Centros de salud")
        ver_otros = casilla_otros.checkbox("○ Otros centros")

        punto_wgs84 = gpd.GeoSeries([fila.geometry], crs=indice.crs).to_crs(epsg=4326).iloc[0]
        mapa_centro = folium.Map(
            location=[punto_wgs84.y, punto_wgs84.x],
            zoom_start=ZOOM_CENTRO,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
            attr="Esri, World Topo Map"
        )
        folium.GeoJson(
            edificios_app.cx[xmin:xmax, ymin:ymax].to_crs(epsg=4326)[["geometry"]],
            style_function=lambda elemento: {"color": "none", "fillColor": "#b0b0b0", "fillOpacity": 1}
        ).add_to(mapa_centro)
        folium.GeoJson(
            isocrona_comoda.to_crs(epsg=4326)[["geometry"]],
            style_function=lambda elemento: {"color": "none", "fillColor": COLOR_COMODO, "fillOpacity": 0.4}
        ).add_to(mapa_centro)
        folium.GeoJson(
            tramos_zona.to_crs(epsg=4326)[["texto", "color", "geometry"]],
            style_function=lambda elemento: {"color": elemento["properties"]["color"], "weight": 3,
                                             "opacity": OPACIDAD_CALLES},
            tooltip=folium.GeoJsonTooltip(fields=["texto"], labels=False)
        ).add_to(mapa_centro)
        folium.GeoJson(
            isocrona_normal.to_crs(epsg=4326)[["geometry"]],
            style_function=lambda elemento: {"color": COLOR_LIMITE, "weight": 3.5, "dashArray": "8 6",
                                             "fillOpacity": 0}
        ).add_to(mapa_centro)

        if ver_fuentes:
            for _, fuente in fuentes_app.cx[xmin:xmax, ymin:ymax].to_crs(epsg=4326).iterrows():
                folium.CircleMarker(location=[fuente.geometry.y, fuente.geometry.x], radius=5, color="black",
                                    weight=1, fill=True, fill_color=COLOR_FUENTE, fill_opacity=1,
                                    tooltip="Fuente de agua").add_to(mapa_centro)
        if ver_refugios:
            for _, refugio in refugios_app.cx[xmin:xmax, ymin:ymax].to_crs(epsg=4326).iterrows():
                if refugio["codigo"] != codigo_centro:
                    texto_refugio = f"Refugio ({refugio['tipo_refugio']}): {refugio['nombre']}"
                    if limpiar_direccion(refugio["direccion"]) != "":
                        texto_refugio += " · " + limpiar_direccion(refugio["direccion"])
                    folium.CircleMarker(location=[refugio.geometry.y, refugio.geometry.x], radius=7, color="white",
                                        weight=1, fill=True, fill_color=COLOR_REFUGIO, fill_opacity=1,
                                        tooltip=texto_refugio).add_to(mapa_centro)
        if ver_salud:
            for _, sanitario in salud_app.cx[xmin:xmax, ymin:ymax].to_crs(epsg=4326).iterrows():
                folium.CircleMarker(location=[sanitario.geometry.y, sanitario.geometry.x], radius=7, color="white",
                                    weight=1, fill=True, fill_color=COLOR_SALUD, fill_opacity=1,
                                    tooltip=f"{sanitario['tipo_salud'].capitalize()}: {sanitario['NOMBRE']} · "
                                            f"{limpiar_direccion(sanitario['direccion'])}").add_to(mapa_centro)
        if ver_otros:
            for _, otro in indice[indice["codigo"] != codigo_centro].cx[xmin:xmax, ymin:ymax].to_crs(epsg=4326).iterrows():
                folium.CircleMarker(location=[otro.geometry.y, otro.geometry.x], radius=5, color="black", weight=1.5,
                                    fill=True, fill_color="white", fill_opacity=1,
                                    tooltip=otro["nombre"]).add_to(mapa_centro)
        folium.CircleMarker(location=[punto_wgs84.y, punto_wgs84.x], radius=11, color="white", weight=2,
                            fill=True, fill_color=COLOR_CENTRO, fill_opacity=1,
                            tooltip=fila["nombre"]).add_to(mapa_centro)
        components.html(mapa_centro.get_root().render(), height=ALTURA_MAPA)

    with columna_derecha:
        if en_plan:
            st.markdown("#### ¿Qué consigue el plan de arbolado?")
            orden_pasos = evolucion["paso"].tolist()
            marca_paso = pd.DataFrame({"paso": [paso_elegido.split(" (")[0]]})
            evolucion["texto_temperatura"] = evolucion["temperatura"].round(1).astype(str) + " °C"
            evolucion["texto_confort"] = evolucion["confort"].round(1).astype(str) + " %"
            temperatura_final = evolucion["temperatura"].iloc[-1]
            confort_final = evolucion["confort"].iloc[-1]
            eje_pasos = alt.X("paso:O", sort=orden_pasos, title=None, axis=alt.Axis(labelAngle=0, labelFontSize=13))

            st.markdown(f'<p style="font-size:16px; margin-bottom:0"><b>Temperatura de su entorno:</b> '
                        f'{temperatura_hoy:.1f} → {temperatura_final:.1f} °C '
                        f'({temperatura_final - temperatura_hoy:+.1f} °C de hoy a la fase 3)</p>',
                        unsafe_allow_html=True)
            linea_temperatura = alt.Chart(evolucion).mark_line(point=True, color="#fd8d3c", strokeWidth=3).encode(
                x=eje_pasos,
                y=alt.Y("temperatura:Q", scale=alt.Scale(zero=False, padding=30), title="°C"),
                tooltip=[alt.Tooltip("paso:O", title="Fase"), alt.Tooltip("temperatura:Q", title="°C")]
            )
            valores_temperatura = alt.Chart(evolucion).mark_text(dy=-14, fontSize=13, color="#fd8d3c").encode(
                x=eje_pasos, y="temperatura:Q", text="texto_temperatura:N")
            marca_temperatura = alt.Chart(marca_paso).mark_rule(color=COLOR_CENTRO, strokeWidth=3,
                                                                opacity=0.6).encode(x=alt.X("paso:O", sort=orden_pasos))
            st.altair_chart((marca_temperatura + linea_temperatura + valores_temperatura).properties(height=200),
                            use_container_width=True)

            st.markdown(f'<p style="font-size:16px; margin-bottom:0"><b>Caminable con comodidad:</b> '
                        f'{confort_hoy:.0f} % → {confort_final:.0f} % '
                        f'({confort_final - confort_hoy:+.1f} puntos de hoy a la fase 3)</p>',
                        unsafe_allow_html=True)
            linea_confort = alt.Chart(evolucion).mark_line(point=True, color=COLOR_COMODO, strokeWidth=3).encode(
                x=eje_pasos,
                y=alt.Y("confort:Q", scale=alt.Scale(zero=False, padding=30), title="%"),
                tooltip=[alt.Tooltip("paso:O", title="Fase"), alt.Tooltip("confort:Q", title="%")]
            )
            valores_confort = alt.Chart(evolucion).mark_text(dy=-14, fontSize=13, color=COLOR_COMODO).encode(
                x=eje_pasos, y="confort:Q", text="texto_confort:N")
            marca_confort = alt.Chart(marca_paso).mark_rule(color=COLOR_CENTRO, strokeWidth=3,
                                                            opacity=0.6).encode(x=alt.X("paso:O", sort=orden_pasos))
            st.altair_chart((marca_confort + linea_confort + valores_confort).properties(height=200),
                            use_container_width=True)
        else:
            st.markdown("#### ¿Qué necesita su entorno?")
            st.markdown(f'<p style="font-size:22px"><b>{fila["medida_texto"]}</b></p>', unsafe_allow_html=True)
            st.caption("El plan de arbolado de 50 zonas no llega a su entorno. Esta es la medida que, según el "
                       "modelo, más le ayudaría.")

        st.markdown("#### Servicios a pie")
        for servicio, sufijo, color, mostrar_nombre in [("Fuente", "agua", COLOR_FUENTE, False),
                                                        ("Refugio", "refugio", COLOR_REFUGIO, True),
                                                        ("Centro de salud", "salud", COLOR_SALUD, True)]:
            if sufijo == "agua":
                direccion_servicio = ""
            else:
                direccion_servicio = fila[f"direccion_{sufijo}"]
            linea = texto_servicio(servicio, fila[f"dist_{sufijo}"], fila[f"nombre_{sufijo}"],
                                   direccion_servicio, mostrar_nombre)
            st.markdown(f'<p style="font-size:16px; margin:3px 0"><span style="color:{color}; font-size:20px">●</span> '
                        f'{linea}</p>', unsafe_allow_html=True)

    st.subheader("¿Por qué está en riesgo hoy?")
    columna_componentes, columna_palancas = st.columns(2)

    with columna_componentes:
        st.markdown("#### Los componentes del riesgo (hoy)")
        st.caption("Los cuatro componentes del índice, de 0 (el mejor de Madrid) a 1 (el peor).")
        componentes = pd.DataFrame({
            "nombre": ["Calor de su entorno", "Personas expuestas", "Vulnerabilidad de sus usuarios",
                       "Falta de protección cerca"],
            "valor": [fila["peligro"], fila["exposicion"], fila["vulnerabilidad"], 1 - fila["capacidad"]]
        })
        componentes["componente"] = componentes["nombre"] + "  " + componentes["valor"].round(2).astype(str)
        grafico_componentes = alt.Chart(componentes).mark_bar(color="#fd8d3c").encode(
            x=alt.X("valor:Q", scale=alt.Scale(domain=[0, 1]), title=None),
            y=alt.Y("componente:N", sort=None, title=None, axis=alt.Axis(labelLimit=300, labelFontSize=13)),
            tooltip=[alt.Tooltip("nombre:N", title="Componente"), alt.Tooltip("valor:Q", title="Valor", format=".2f")]
        ).properties(height=210)
        st.altair_chart(grafico_componentes, use_container_width=True)

    with columna_palancas:
        st.markdown("#### ¿Qué calienta su entorno? (hoy)")
        st.caption("Según el modelo (SHAP): grados que suma (rojo) o resta (azul) cada factor a su entorno, "
                   "comparado con la media de Madrid.")
        palancas = []
        for clave, (texto_calienta, texto_enfria, texto_neutro) in TEXTO_PALANCA.items():
            grados = round(fila_diagnostico[clave], 2)
            if abs(grados) < 0.01:
                palancas.append({"factor": f"{texto_neutro}: sin efecto", "grados": 0.0, "efecto": "Sin efecto"})
            elif grados > 0:
                palancas.append({"factor": f"{texto_calienta}  +{grados} °C", "grados": grados, "efecto": "Calienta"})
            else:
                palancas.append({"factor": f"{texto_enfria}  {grados} °C", "grados": grados, "efecto": "Enfría"})
        palancas = pd.DataFrame(palancas)
        barras_palancas = alt.Chart(palancas).mark_bar().encode(
            x=alt.X("grados:Q", title="°C"),
            y=alt.Y("factor:N", sort=None, title=None, axis=alt.Axis(labelLimit=300, labelFontSize=13)),
            color=alt.Color("efecto:N",
                            scale=alt.Scale(domain=["Calienta", "Enfría", "Sin efecto"],
                                            range=["#e31a1c", "#1f77b4", "#9e9e9e"]),
                            legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("factor:N", title="Factor"), alt.Tooltip("grados:Q", title="°C")]
        )
        linea_cero = alt.Chart(pd.DataFrame({"cero": [0]})).mark_rule(color="#bdbdbd").encode(x="cero:Q")
        st.altair_chart((barras_palancas + linea_cero).properties(height=210), use_container_width=True)

st.divider()
st.markdown(":gray[Datos: Landsat 8 y 9 (veranos 2023-2026), Sentinel-2, Catastro, Urban Atlas 2021 (Copernicus), "
            "OpenStreetMap, Ayuntamiento de Madrid y Comunidad de Madrid (datos abiertos).]")
st.markdown(":gray[**Proyecto final de Ironhack Data Analytics** · Juan Carlos Del Mar Lostanau, 2026]")