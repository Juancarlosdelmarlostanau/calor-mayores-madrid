# Calor y mayores en Madrid

En verano, Madrid no es igual de caliente para todos. Este proyecto mide cuánto calor soportan las residencias y los centros de mayores de Madrid, qué encuentran sus usuarios en 15 minutos andando y propone dónde plantar árboles primero.

**Aplicación en línea:** [calor-mayores-madrid.streamlit.app](https://calor-mayores-madrid.streamlit.app/)

## Objetivo

- Desarrollar un modelo de Machine Learning que explique la temperatura de superficie de verano de Madrid a partir de la forma urbana (vegetación, edificios, terreno y entorno).
- Usar el modelo como motor de un **simulador de arbolado** y de un **índice de riesgo por calor** de cada centro de mayores, calculado sobre su entorno real de 15 minutos andando.
- Proponer un **plan de arbolado priorizado**: qué zonas de la ciudad conviene intervenir primero para proteger a más mayores con el mismo esfuerzo.
- Integrarlo todo en una aplicación interactiva pensada para un público no técnico (Ayuntamiento, Comunidad de Madrid y operadores de residencias).

## Hipótesis

1. **H1:** la vegetación y la forma de los edificios explican la mayor parte de la temperatura de superficie.
2. **H2:** el efecto de la vegetación no es lineal: existe un umbral, en torno a un NDVI de 0,2, a partir del cual empieza a enfriar.
3. **H3:** aumentar la copa de árboles reduce más la temperatura en el entorno de los centros más calientes.

## Datos

| Dato | Fuente | Carpeta en `raw/` |
|---|---|---|
| Temperatura de superficie (Landsat 8 y 9, Collection 2 Level 2, banda ST_B10), julio y agosto de 2023 a 2026 | [Google Earth Engine](https://earthengine.google.com/), exportado a Google Drive | `dato4y5/lst_summer_madrid_2023_2026.tif` |
| NDVI y albedo (Sentinel-2, 10 m), mismos veranos | [Google Earth Engine](https://earthengine.google.com/), exportado a Google Drive | `dato4y5/` |
| Muestra de 5.000 puntos para el modelo beta (temperatura, NDVI, albedo y elevación) | Google Earth Engine | `gee/lst_samples_beta.csv` |
| Registro de centros de atención social (residencias, centros de día y hogares y clubes) | [Comunidad de Madrid, datos abiertos](https://datos.comunidad.madrid/) | `dato2y3/` |
| Edificios y partes de edificio (año de construcción, uso y número de plantas) | [Catastro INSPIRE](https://www.catastro.hacienda.gob.es/webinspire/index.html), municipio 28900 | `dato6/` |
| Copa de árboles (Street Tree Layer) y máscara urbana, 2021 | [Copernicus Urban Atlas](https://land.copernicus.eu/en/products/urban-atlas) | `dato7/7253/` |
| Usos del suelo (viario, ferrocarril, agua, suelo desnudo), 2021 | [Copernicus Urban Atlas](https://land.copernicus.eu/en/products/urban-atlas) | `dato7/9083/` |
| Modelo digital del terreno MDT05 (9 hojas, unidas en un ráster de 25 m) | [IGN, Centro de Descargas del CNIG](https://centrodedescargas.cnig.es/) | `dato8/` |
| Arbolado municipal (un punto por árbol, con su altura) | [Portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es/) (300761) | `arbolado/` |
| Fuentes de agua de beber | [Portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es/) (300051) | `fuentes/` |
| Centros de atención médica (centros de salud y hospitales) | [Portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es/) (212769) | `centrosalud/` |
| Mercados municipales (refugios climáticos) | [Portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es/) (200967) | `mercados/` |
| Límites de término municipal, distritos, barrios y secciones censales | [Portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es/) | `limites/` |
| Red peatonal y parques, con un margen de 2 km alrededor del término municipal | [OpenStreetMap](https://www.openstreetmap.org/), descargado con `osmnx` | `osm/` |

La carpeta `raw/` no se incluye en el repositorio por su tamaño. Para reproducir el proyecto desde cero hay que descargar cada dato desde su fuente y guardarlo en la carpeta indicada. La red peatonal y los parques se descargan con el notebook `00_data_collection.ipynb`. La carpeta `clean/` sí se incluye, con todos los datos ya procesados que usan los notebooks finales y la aplicación.

## Metodología

### 1. Centros de mayores
- Del registro de la Comunidad de Madrid se seleccionan los centros de Madrid capital, del sector de personas mayores, residenciales o de día.
- Se eliminan 11 centros sin coordenadas (unas 1.900 plazas).
- Resultado: **439 centros**: 165 residencias, 154 centros de día, 112 centros de mayores (hogares y clubes) y 8 viviendas tuteladas.

### 2. Hexágonos y variables (feature engineering)
- Madrid se divide en **5.567 hexágonos H3 de resolución 9** (unos 0,11 km² cada uno). Los hexágonos tienen todos el mismo tamaño y forma, y sus vecinos están a la misma distancia, por lo que permiten comparar zonas de forma justa.
- Se conservan los **2.931 hexágonos urbanos** según la máscara del Urban Atlas, más los que contienen algún centro.
- Para cada hexágono se calculan la temperatura media de superficie (target) y **14 variables**: NDVI, albedo, % edificado, % industrial, plantas medias, año medio de construcción, % de copa de árboles, altura de los árboles, árboles por hectárea, elevación, distancia a un parque grande (de al menos 1 ha), % de viario, distancia al agua y % de suelo desnudo.
- Los edificios se recortan por los bordes de los hexágonos para repartir su superficie entre los hexágonos que ocupan.

### 3. Análisis exploratorio
- Distribución de la temperatura y de las variables, valores atípicos (extremos reales, no errores) y correlaciones.
- Se elimina la edificabilidad por su alta correlación con el % edificado (0,84).
- El NDVI es la variable más relacionada con la temperatura (correlación de −0,66), seguido del suelo desnudo (+0,63).

### 4. Modelo beta
- Prueba inicial con 5.000 puntos aleatorios y solo 3 variables (NDVI, albedo y elevación), para comprobar que la forma urbana explica parte de la temperatura.

### 5. Modelado
- **Validación espacial:** el test lo forman 5 distritos completos (Barajas, Hortaleza, Moratalaz, Retiro y Villaverde, 814 hexágonos) que el modelo no ve hasta el final. Los modelos se comparan con validación cruzada agrupada por distritos (`GroupKFold`, 5 particiones), para evitar que el modelo copie a los hexágonos vecinos y se infle el R².
- **Ronda 1:** comparación de 11 modelos con su configuración por defecto (regresión lineal, Ridge, Lasso, KNN, SVR, árbol de decisión, Random Forest, Extra Trees, Gradient Boosting, HistGradientBoosting y XGBoost).
- **Ronda 2:** búsqueda aleatoria de hiperparámetros (`RandomizedSearchCV`, 100 combinaciones por modelo) en los 6 mejores.
- **Ronda 3:** búsqueda fina en cuadrícula (`GridSearchCV`) alrededor de los mejores valores de los 3 mejores.
- **Métricas:** R², MAE y RMSE, en °C.
- **Interpretación con SHAP** (`TreeExplainer`): cuántos grados suma o resta cada variable en cada hexágono.

### 6. Modelo final
**Gradient Boosting** con 14 variables: `learning_rate=0.06`, `max_depth=2`, `min_samples_leaf=4`, `n_estimators=550`, `subsample=0.65`, `random_state=0`. Es el de mejor R² en la validación y el más sencillo de los finalistas (árboles de profundidad 2).

### 7. Simulador de arbolado
- Simula tres fases del plan, que aumentan el % de copa de árboles: **+5, +10 y +20 puntos**.
- Al plantar árboles sube también la vegetación que mide el satélite: el NDVI aumenta 0,0036 por cada punto de copa, según la relación observada en los hexágonos urbanos.
- Dos límites de realismo: la copa no puede superar el espacio libre del hexágono, y el NDVI no puede superar el máximo urbano observado (0,72), para que el modelo no prediga fuera de lo que ha aprendido.
- Solo cambian la copa y el NDVI, así que los resultados son conservadores.

### 8. Isócronas: el entorno de 15 minutos andando
- **Isócrona normal:** zona a la que se llega andando por la red de calles en 15 minutos a 0,8 m/s, la velocidad media al caminar de las mujeres de 65 años o más según Asher y colaboradores (2012) (720 m de recorrido). Respeta las barreras reales, como autovías, vías de tren o parques cerrados.
- **Nodo puerta:** cada centro sale a la red por un nodo virtual unido a todos los cruces a menos de 100 m, para no quedar atrapado en un camino mal conectado.
- **Isócrona confortable:** la parte del recorrido que se puede hacer sin exceso de calor. Cada tramo de calle tiene una "longitud vivida" que penaliza el calor: coste = longitud × (1 + (α − 1) × calor del tramo), donde el calor del tramo va de 0 (calle menos caliente) a 1 (calle muy caliente), escalado entre los percentiles 5 y 95 de la temperatura urbana. Con α = 1,5, un metro con el máximo calor se vive como 1,5 metros. Sigue la formulación de CoolWalks (Wolf, Vierø y Szell, 2025) y la idea de una isócrona que evita la exposición al calor (Huber y colaboradores, 2025).

### 9. Índice de riesgo
- Marco del IPCC: **Riesgo = Peligro × Exposición × Vulnerabilidad × (1 − Capacidad)**, con cada componente entre 0 y 1.
  - **Peligro:** temperatura media del entorno de 15 minutos.
  - **Exposición:** plazas del centro, comparadas dentro de su tipo.
  - **Vulnerabilidad:** tipo de centro (grado de dependencia de sus usuarios) y antigüedad del edificio.
  - **Capacidad:** distancia andando a la fuente, al refugio climático y al centro de salud más cercanos, sombra de árboles y % de recorrido confortable.
- Se multiplica por (1 − Capacidad) en lugar de dividir entre la capacidad, para evitar riesgos infinitos.
- Los refugios climáticos son los 44 mercados municipales y los 112 centros de mayores, en línea con los refugios del verano de 2026.
- Prioridad por percentiles: **alta** a partir del percentil 80 (88 centros), **media** del 50 al 80 (131) y **baja** el resto (220).

### 10. Priorización: el plan de arbolado
- **Diagnóstico con SHAP** del entorno de cada centro: qué lo calienta (falta de vegetación, suelo desnudo, edificios bajos o lejanía de un parque grande) y qué medida le corresponde.
- **Optimización:** cada hexágono candidato se valora por la bajada de temperatura que consigue, multiplicada por el riesgo de los centros cuyo entorno lo contiene. Se eligen las **50 zonas** con más valor.
- **Antes y después:** temperatura y confort del entorno de cada centro en las tres fases del plan.

## Resultados

### Modelo

| Etapa | Modelo | Evaluación | R² | MAE (°C) | RMSE (°C) |
|---|---|---|---|---|---|
| Modelo beta | Regresión lineal | 5.000 puntos, 3 variables | 0,262 | 2,23 | 2,81 |
| Modelo beta | Random Forest | 5.000 puntos, 3 variables | 0,400 | 1,97 | 2,53 |
| Ronda 1 | Regresión lineal | Validación por distritos | 0,608 | 1,05 | 1,40 |
| Ronda 1 | Gradient Boosting | Validación por distritos | 0,654 | 0,98 | 1,32 |
| Ronda 2 | Gradient Boosting (Random Search) | Validación por distritos | 0,680 | 0,94 | 1,27 |
| **Ronda 3** | **Gradient Boosting (Grid Search)** | **Validación por distritos** | **0,684** | **0,94** | **1,26** |
| **Test** | **Gradient Boosting final** | **5 distritos no vistos** | **0,819** | **1,03** | **1,43** |

- **Validación (R² = 0,684):** es la nota con la que se eligió el modelo, evaluado sobre distritos que no había visto durante el entrenamiento. Es la cifra más prudente.
- **Test (R² = 0,819):** es la nota final, sobre 5 distritos apartados desde el principio y usados una sola vez. Es más alta que la validación por los distritos concretos que forman el test: tienen una gran variedad de temperaturas (de 42 °C en Retiro a 48 °C en Barajas), que el modelo ordena bien. El error medio (1,03 °C) es similar al de la validación (0,94 °C).
- Los cuatro modelos de conjuntos de árboles empatan en la ronda 1 (diferencias menores que su desviación entre distritos). El ajuste de hiperparámetros mejora el R² en 0,03 puntos.

### Hipótesis

- **H1, se cumple:** la vegetación es lo que más explica la temperatura (NDVI, copa, altura y densidad de árboles mueven la predicción 1,8 °C de media), seguida de la forma de los edificios (1,3 °C).
- **H2, se cumple:** por debajo de un NDVI de 0,2 el efecto de la vegetación es casi constante; a partir de ahí enfría cada vez más, hasta −7 °C en los parques.
- **H3, se cumple:** los centros con el entorno más caliente son también donde plantar rinde más. 7 de los 10 centros más calientes están entre los que más bajarían su temperatura, y los distritos más calurosos (Vicálvaro, Villaverde, Villa de Vallecas) son los que más ganan.

### Hallazgos principales

- **El entorno importa más que el edificio:** la temperatura media del entorno de los centros va de 40,8 a 48,2 °C, y 112 centros no tienen ningún refugio climático a menos de 1 km andando.
- **El riesgo se concentra en el sur y el sureste:** los centros de prioridad alta están sobre todo en Latina, Carabanchel, Usera, Villaverde, Vallecas y Vicálvaro. El de mayor riesgo es la residencia Doctor González Bueno (601 plazas), con mucho calor y casi ninguna protección cerca.
- **El índice es robusto:** el orden de los centros apenas cambia al usar otro límite de distancia a los servicios (Spearman de 1,0) o una escala de vulnerabilidad más sencilla (0,995).
- **Plantar árboles es la medida principal:** según el diagnóstico con SHAP, es la medida que más necesita el entorno de 206 centros, entre ellos 73 de los 88 de prioridad alta.
- **Pocas zonas bien elegidas llegan a muchos centros:** las 50 zonas del plan (un 1,8 % de las calles) alcanzan el entorno de 104 centros, 53 de ellos de prioridad alta, con 9.111 plazas y 6.537 socios de centros de mayores. La selección es 4,8 veces mejor que elegir zonas al azar.
- **Lo que consigue el plan:** en las zonas elegidas, la temperatura de superficie baja 0,70, 1,02 y 1,75 °C en las fases 1, 2 y 3. En el conjunto del entorno de 15 minutos de cada centro, la bajada media es de 0,20, 0,29 y 0,52 °C, y el recorrido confortable gana de media 0,7, 1,1 y 2,2 puntos (2,9 en los centros de prioridad alta, y hasta 8,5 en el mejor caso).
- **El arbolado no basta solo:** incluso con la fase 3, los entornos más calientes siguen siéndolo. Allí hacen falta además refugios y fuentes.

## Aplicación

Aplicación interactiva desarrollada con **Streamlit**, con tres pestañas:

- **Resumen:** mapa de los 439 centros por prioridad, con filtros por tipo de centro y prioridad. Muestra qué necesita el entorno de cada centro y la lista de centros ordenada por riesgo, con su confort y su refugio más cercano.
- **La ciudad:** dos mapas de la temperatura de superficie de Madrid con el mismo código de colores: hoy y con el potencial máximo de cada fase, es decir, plantando en todos los hexágonos que forman el entorno de 15 minutos de algún centro (fuera de esos entornos no se planta). Incluye la distribución de la temperatura de las zonas y la bajada por distrito.
- **Un centro:** el entorno de 15 minutos andando de un centro, con sus calles coloreadas por temperatura, la zona confortable, las fuentes, los refugios y los centros de salud más cercanos andando. Un deslizador muestra la evolución con el plan de arbolado realista (las 50 zonas elegidas por el optimizador), y dos gráficos explican por qué está en riesgo hoy: los componentes del índice y los factores que calientan su entorno según el modelo.

### Cómo ejecutarla

La aplicación está publicada en **Streamlit Community Cloud** y puede usarse directamente desde el navegador: [calor-mayores-madrid.streamlit.app](https://calor-mayores-madrid.streamlit.app/)

Para ejecutarla en local (opcional):

1. Instalar las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

2. Desde la carpeta raíz del proyecto, lanzar la aplicación:

   ```bash
   streamlit run app/app.py
   ```

   Si el comando `streamlit` no se reconoce, se puede usar `python -m streamlit run app/app.py`

El archivo `requirements.txt` de la raíz incluye todas las librerías del proyecto (notebooks, scripts y aplicación). El de la carpeta `app/` incluye solo las que necesita la aplicación y es el que usa Streamlit Community Cloud.

## Estructura del proyecto

```
calor-mayores-madrid/
├── raw/                                        # Datos originales (no incluidos, ver la sección Datos)
├── clean/
│   ├── centros_mayores.gpkg                    # 439 centros de mayores limpios
│   ├── hexagonos_h3.gpkg                       # Hexágonos H3 con la temperatura y las 14 variables
│   ├── centros_simulacion.gpkg                 # Bajada de temperatura de cada centro por fase
│   ├── isocronas_normales.gpkg                 # Entorno de 15 minutos andando de cada centro
│   ├── isocronas_confortables.gpkg             # Parte confortable de cada entorno
│   ├── isocronas_confortables_plan.gpkg        # Parte confortable con cada fase del plan
│   ├── centros_hexagonos.csv                   # Hexágonos que forman el entorno de cada centro
│   ├── indice_riesgo.gpkg                      # Índice de riesgo y sus componentes
│   ├── servicios_fuentes.gpkg                  # Fuentes de agua operativas
│   ├── servicios_refugios.gpkg                 # Refugios climáticos (mercados y centros de mayores)
│   ├── servicios_salud.gpkg                    # Centros de salud y hospitales
│   ├── priorizacion_diagnostico.csv            # Diagnóstico SHAP y medida de cada centro
│   ├── priorizacion_hexagonos.gpkg             # Hexágonos candidatos y zonas elegidas
│   ├── priorizacion_centros.csv                # Antes y después de cada centro
│   ├── priorizacion_confort.csv                # Confort de cada centro por fase
│   ├── priorizacion_curva.csv                  # Centros alcanzados según el número de zonas
│   └── app_*.parquet, app_distritos.gpkg       # Capas preparadas para la aplicación
├── notebooks/
│   ├── 00_data_collection.ipynb                # Descarga de la red peatonal y los parques (OSM)
│   ├── 01_data_cleaning_centros.ipynb          # Limpieza de los centros de mayores
│   ├── 02_feature_engineering.ipynb            # Hexágonos H3 y cálculo de las 14 variables
│   ├── 03_eda.ipynb                            # Análisis exploratorio
│   ├── 04_beta_model.ipynb                     # Modelo beta con 3 variables
│   ├── 05_modelo.ipynb                         # Comparación, ajuste, evaluación y SHAP
│   ├── 06_simulador.ipynb                      # Simulador de arbolado
│   ├── 07_isocronas.ipynb                      # Isócronas normales y confortables
│   ├── 08_indice_riesgo.ipynb                  # Índice de riesgo por centro
│   └── 09_priorizacion.ipynb                   # Diagnóstico, optimización y plan de arbolado
├── scrips/
│   ├── config.py                               # Rutas y sistema de coordenadas del proyecto
│   ├── limpieza_centros.py                     # Funciones de limpieza de los centros
│   ├── variables_hexagonos.py                  # Funciones de cálculo de las variables
│   ├── simulador.py                            # Funciones del simulador de arbolado
│   ├── isocronas.py                            # Funciones de las isócronas
│   ├── indice_riesgo.py                        # Funciones del índice de riesgo
│   └── priorizacion.py                         # Funciones de la priorización
├── models/
│   └── modelo_gradient_boosting.pkl            # Modelo final, sus variables y la mediana del año de train
├── app/
│   ├── app.py                                  # Aplicación de Streamlit
│   └── requirements.txt                        # Librerías de la aplicación (Streamlit Community Cloud)
├── .streamlit/
│   └── config.toml                             # Tema de colores de la aplicación
├── presentation/                               # Presentación del proyecto
├── requirements.txt                            # Librerías de todo el proyecto
└── README.md
```

Cada script reproduce exactamente el resultado de su notebook: al final de cada notebook se comprueba que ambos dan el mismo resultado.

## Limitaciones

- **Temperatura de superficie, no del aire:** el satélite mide lo caliente que está el suelo, no la temperatura que siente una persona a la sombra. Ambas están relacionadas, pero no son lo mismo.
- **Asociaciones, no causas:** el modelo aprende cómo se relaciona la forma urbana con la temperatura en Madrid. El simulador estima el efecto de plantar árboles según esa relación, no lo demuestra.
- **Simulación conservadora:** solo cambian la copa de árboles y el NDVI. No se simulan otras medidas, como tejados claros o ajardinar solares.
- **Desfase entre fuentes:** el Urban Atlas es de 2021 y la temperatura de 2023 a 2026. Por ejemplo, el lago de la Casa de Campo aparece como suelo sin uso.
- **Centros excluidos:** 11 centros sin coordenadas (unas 1.900 plazas) quedan fuera del estudio.
- **Plazas no comparables:** las plazas de los centros de mayores son socios o aforo, no plazas de atención. Por eso la exposición se compara dentro de cada tipo de centro.
- **Refugios:** Madrid no tiene una lista oficial unificada de refugios climáticos, y su definición sigue siendo objeto de debate público en el Ayuntamiento. En este proyecto se usan como refugios los mercados municipales y los centros de mayores, en línea con el plan municipal contra el calor de 2026.
- **Supuestos del índice:** el orden de vulnerabilidad por tipo de centro se basa en el metaanálisis de Bouchama et al. (2007), que identifica la dependencia (estar encamado o no poder valerse por uno mismo) como el principal factor de riesgo de muerte en olas de calor; los valores concretos de la escala son un supuesto. El valor α = 1,5 de la isócrona confortable sigue el modelo CoolWalks (Wolf, Vierø y Szell, 2025), en el que un metro con el máximo calor se vive como 1,5 metros; sus autores señalan que α es difícil de medir en la práctica. Las pruebas de sensibilidad muestran que el orden de los centros apenas cambia con otra escala de vulnerabilidad (Spearman de 0,995) ni con otros valores de α (de 0,90 a 0,95).
- **Viario:** el Urban Atlas solo separa como vía las calles de más de 10 m de ancho, por lo que el % de viario refleja sobre todo avenidas.

## Próximos pasos

- **Temperatura del aire:** combinar la temperatura de superficie con estaciones meteorológicas o modelos de temperatura del aire.
- **Variables de contexto:** añadir al modelo la media de las variables en los hexágonos vecinos.
- **Más medidas en el simulador:** tejados claros o verdes, ajardinar solares y nuevos parques, además del arbolado.
- **Mayores en sus casas:** extender el análisis a toda la población mayor por sección censal, no solo a la que usa centros.
- **Métodos espaciales:** aplicar regresión geográficamente ponderada (GWR) para ver cómo cambia el efecto de cada variable por zonas.

## Referencias

- Asher, L., Aresu, M., Falaschetti, E. y Mindell, J. (2012). Most older pedestrians are unable to cross the road in time: a cross-sectional study. *Age and Ageing*, 41(5), 690-694. https://doi.org/10.1093/ageing/afs076
- Annerstedt van den Bosch, M. et al. (2016). Development of an urban green space indicator and the public health rationale. *Scandinavian Journal of Public Health*, 44(2), 159-167. https://doi.org/10.1177/1403494815615444
- Bouchama, A. et al. (2007). Prognostic factors in heat wave related deaths: a meta-analysis. *Archives of Internal Medicine*, 167(20), 2170-2176. https://doi.org/10.1001/archinte.167.20.ira70009
- Huber, J., Ludwig, C., Foshag, K., Kolaxidis, N., Zipf, A. y Lautenbach, S. (2025). Accessibility for pedestrians under heat stress – the example of Heidelberg, Germany. *AGILE: GIScience Series*, 6, 4. https://doi.org/10.5194/agile-giss-6-4-2025
- Pozo Menéndez, E., Cambra-Rufino, L., Jiménez Martín, D. y Zarco Colón, J. (2024). El papel de la arquitectura en los centros de atención a la dependencia. *Revista Española de Discapacidad*, 12(1), 99-118. https://doi.org/10.5569/2340-5104.12.01.05
- Wolf, H., Vierø, A. R. y Szell, M. (2025). CoolWalks for active mobility in urban street networks. *Scientific Reports*, 15, 14911. https://doi.org/10.1038/s41598-025-97200-2

## Autor

**Juan Carlos Del Mar Lostanau**
Arquitecto (Perú) con estudios de máster en Planeamiento Urbano, especialidad en Estudios Urbanos. Estudiante de Data Analytics en Ironhack, con interés en la aplicación de datos y Machine Learning al análisis espacial, el urbanismo y las ciudades inteligentes.