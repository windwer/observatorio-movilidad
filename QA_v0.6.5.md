# QA v0.6.5 · Product Review

## Cambios verificados

- El mapa ocupa una columna dominante y pasa a 600 px de alto en escritorio; mantiene ajustes responsive.
- La ficha de línea calcula longitud a partir de la geometría `shape` GTFS y velocidad comercial como longitud / duración cabecera–última parada.
- El visor semanal muestra medias de expediciones para lunes–jueves, viernes, sábado y domingo.
- La agrupación semanal usa el nombre público (`route_short_name`) y conserva todos los `route_id` equivalentes, incluidos cambios de fin de semana.
- La población de cobertura continúa siendo la estimación deduplicada sobre la red peatonal OSM real; no se conectan APIs de transporte externas.

## Pruebas ejecutadas

- `tests.test_route_insights_v065`: 2 pruebas OK.
- `node --check static/app.js`: OK.
- `node --check static/offline_map.js`: OK.
- `py_compile app.py route_insights.py`: OK.
- Comprobación de coherencia del lanzador: `/api/health`, `/api/version` y `launcher.py` declaran `0.6.5`.

## Caso DEMO comprobado

Para Irunbus L1 (15/10/2026), la demo devuelve 5,49 km, 13,7 km/h y 24,0 minutos de recorrido mediano; la frecuencia media es 60 expediciones/día en lunes–jueves, 52 en viernes, 34 en sábado y 26 en domingo. Son horarios programados de DEMO, no certificación de servicio prestado.
