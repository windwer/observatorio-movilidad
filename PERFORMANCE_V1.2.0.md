# Rendimiento · v1.2.0

Implementación local del 28/10/2026. Las seis prioridades están implementadas.

## Cambios

1. El mapa espera sólo al análisis mensual necesario para elegir una fecha con
   servicio. Si se elige fecha exacta, se solicita directamente. Calendario,
   comparativa y detalle de línea se completan independientemente. El lanzador
   valida readiness y población tabular sin bloquear la apertura construyendo
   todo el grafo provincial.
2. Una caché de cliente acotada a 96 respuestas y cinco minutos reutiliza datos
   según los parámetros reales. Cambiar línea no repite cobertura anual ni la
   comparativa común. Las importaciones invalidan la caché. Las generaciones de
   selección impiden pintar resultados atrasados. El servidor reutiliza también
   métricas, frecuencias y cobertura anual.
3. `access_cache.py` guarda geometrías y población por parada, más los índices de
   residentes alcanzables para coberturas únicas. Es SQLite comprimido en el
   volumen de estado, compartido entre web y worker. Su namespace contiene SHA-256
   de censos, edificios, red y anclajes. Las lecturas de paradas ya preparadas no
   necesitan construir el grafo en el proceso web.
4. La cobertura de línea ejecuta Dijkstra sin construir buffers, uniones ni
   polígonos SVG. Selecciona candidatos en un radio conservador y conserva la
   prueba final de distancia por red. Une identificadores de residentes para
   eliminar duplicados. No suma las poblaciones de las paradas.
5. Las importaciones y las releases materializan primera salida, última llegada
   y origen de cada viaje. Los análisis reutilizan estos datos manteniendo
   servicios, sentidos, excepciones y tiempos superiores a 24:00. Los días con
   el mismo feed y conjunto de servicios reutilizan sus salidas durante el
   cálculo mensual/semanal. Las bases antiguas siguen teniendo un camino de
   lectura compatible.
6. El mapa conserva la geometría GTFS completa y aplica Douglas-Peucker al
   dibujar, con tolerancia de 0,6 píxeles al zoom actual. Conserva extremos y
   recupera detalle al acercar. Reutiliza nodos SVG por recorrido/parada, almacena
   proyecciones y agrupa la actualización de teselas por frame. La API comprime
   las respuestas con gzip. Si una vista supera el presupuesto de 110 teselas,
   reduce su nivel de detalle en vez de dejar el mapa base vacío; se intenta
   el proveedor alternativo si el primero no responde en seis segundos.

## Artefactos preparados

- Release local: `gipuzkoa-2026-10-28-v1.2.0`, 162 feeds, 616.554 resúmenes de
  expediciones, 724.797 habitantes. La release anterior permanece disponible.
- Caché: 968 coordenadas distintas del histórico, con niveles de 5 y 10 minutos,
  geometrías y conjuntos de población. Tamaño aproximado: 18 MB.
- La caché se puede borrar y reconstruir. Nunca sustituye los GTFS o la
  cartografía original. Debe permanecer fuera del repositorio y del volumen
  inmutable de datos.

## Mediciones reproducibles

`scripts/benchmark_optimizations.py` ejecuta los algoritmos de la etiqueta
`v1.1.0` y los nuevos sobre la misma base real. Comprueba igualdad de resultados
mensuales, habitantes, municipios, residentes y paradas conectadas. Los tiempos
de cobertura comparan cálculo previo bajo demanda frente a artefactos preparados;
no son una estimación de velocidad del primer precálculo.

| Operación | v1.1.0 (ms) | Optimizada (ms) |
|---|---:|---:|
| Mes Ekialdebus | 600,38 | 84,21 |
| Mes Irunbus | 138,05 | 44,03 |
| Mes Euskotren | 60,99 | 33,33 |
| Mes Errenteria urbano | 62,29 | 32,00 |
| Cobertura Irunbus, 75 paradas | 15.482,07 | 397,90 |
| Cobertura BI05, 35 paradas | 6.521,06 | 166,83 |
| Cobertura Errenteria urbano, 81 paradas | 24.685,54 | 376,50 |

La prueba HTTP ampliada incluyó 20 sesiones durante 60 segundos, cuatro
operadores y 33 URLs de meses, mapas, métricas, frecuencias e isócronas. Resultado:
2.086 peticiones, cero errores, p95 de 316,6 ms y máximo de 792,1 ms. Son medidas
locales con esa carga y esos datos; la carga de teselas externas depende de su
proveedor y de la conexión.

Tras reiniciar el proceso web, una parada precalculada respondió en 437 ms
incluyendo la llamada PowerShell y la lectura inicial del artefacto; las métricas
confirmaron que el grafo web seguía sin cargar. Un mapa BI05 pasó de 24.594 bytes
JSON a 9.363 bytes transferidos con gzip (reducción del 62 %).

Validación final: suite completa de 90 pruebas Python (3 DEMO omitidas) y
6 pruebas JavaScript, todas correctas. También se ejecutaron 21 regresiones de
HTTP, arranque, arquitectura y caché durante la implementación.

La última inspección visual de las teselas quedó pendiente porque la revisión
automática del navegador alcanzó su límite de uso. La lógica de selección y
presupuesto de teselas está cubierta por las pruebas JavaScript; no se afirma
que esta última inspección del proveedor externo se haya completado.

## Preparación y verificación

Para volver a abrir esta entrega desde la raíz del checkout local:

```powershell
.\scripts\start_local.ps1 -ReleaseDirectory "..\..\outputs\releases\gipuzkoa-2026-10-28-v1.2.0" -StateDirectory "..\..\outputs\runtime-v120" -Python "..\..\outputs\Observatorio_Movilidad_historico_completo_v1_20261020\.venv\Scripts\python.exe"
```

El lanzador abre el navegador, inicia web y worker, y elige otro puerto si el
solicitado sigue ocupado. Para otra instalación se pueden indicar otras rutas.

El build admite `--access-cache RUTA_ESTADO/access-cache.sqlite3` para preparar
automáticamente todas las paradas. También puede ejecutarse por separado y se
reanuda reutilizando los resultados ya presentes:

```powershell
python scripts/prepare_accessibility.py --db RUTA_RELEASE/observatorio_real.sqlite3 --geography RUTA_RELEASE/geography --cache RUTA_ESTADO/access-cache.sqlite3
python scripts/benchmark_optimizations.py --db RUTA_RELEASE/observatorio_real.sqlite3 --geography RUTA_RELEASE/geography --cache RUTA_ESTADO/access-cache.sqlite3 --output benchmark.json
python scripts/load_test.py --base http://127.0.0.1:8874 --sessions 20 --seconds 60 --think-ms 500 --mixed --output load.json
python -m unittest discover -q
node --test scripts/test_ui_performance.js
```

El servicio web y el worker deben compartir `OBS_STATE_DB` (su directorio contiene
`access-cache.sqlite3`) y usar la misma release geográfica. No se han cambiado
las velocidades, penalizaciones peatonales o reglas de reparto de población.
