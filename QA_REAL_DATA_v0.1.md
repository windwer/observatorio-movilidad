# QA · paquete GTFS real 0.1

Fecha de comprobación: 19/10/2026.

## Resultado

- **Importación:** OK. Dos feeds en una base SQLite separada de la DEMO.
- **Integridad estructural:** OK en ambos feeds; sin incidencias detectadas por la auditoría GTFS automatizada.
- **Ekialdebus:** 25 rutas, 229 paradas, 4.563 viajes base, 85.991 eventos de parada; calendario 2026-10-12 → 2027-01-10.
- **Irunbus/AUIF:** 5 rutas, 77 paradas, 1.012 viajes base, 15.030 eventos de parada; calendario 2026-10-19 → 2027-01-17.
- **Mapa:** OK con shapes GTFS reales y, cuando falta shape, respaldo a la secuencia de paradas. Sonda 2026-10-16: Ekialdebus 53 trazados / 229 paradas; sonda 2026-10-19: Irunbus 13 trazados / 75 paradas.
- **Métricas de línea:** OK. Se verificaron longitud de shape, tiempo cabecera–última parada, velocidad comercial estimada y frecuencia por categoría de día en una línea de cada operador.
- **Ventana de servicio:** OK. El visor muestra primera salida → última salida, amplitud diaria y expediciones con hora válida; la comparación de dos fechas clasifica por separado cambios de horario y de frecuencia (incluido el caso “más horario, menos frecuencias”).
- **Referencia demográfica:** OK. La base real contiene el CSV Eustat 2025 verificado y sus 109 secciones (150.832 habitantes; Bidasoaldea 77.625; Oarsoaldea 73.207). La referencia se muestra en la parte superior del visor, separada de la cobertura espacial.
- **Reproducibilidad:** OK. Los ZIP entregados y las copias canónicas con SHA-256 se conservan en `data/real/originals/`.
- **Separación DEMO/real:** OK. El arranque real apunta a `data/real/observatorio_real.sqlite3`; el paquete no contiene `data/demo`.

## Límites aceptados para esta entrega

- La fecha de corte histórica del visor sigue siendo 18/10/2026. La captura AUIF del 19/10/2026 se etiqueta como planificación para esa fecha y posteriores.
- GTFS describe servicio programado; no acredita prestación, puntualidad, demanda ni validación documental histórica.
- Eustat aporta población por sección censal, pero no aporta por sí solo la geometría necesaria para saber qué habitantes están dentro de una isócrona de red.
- Solo se incluye la red peatonal OSM. Al no haber polígonos censales ni edificios residenciales reales en los archivos entregados, la población cubierta por recorrido y por parada queda en estado `incomplete_geography` y no se sustituye por un número inventado.

## Pruebas ejecutadas

- `py_compile` sobre `app.py`, `engine.py`, `route_insights.py` y `launcher.py`: OK.
- Suite `test_engine.py`: 9 pruebas, OK.
- Comprobación del ZIP final: base presente, 2 feeds, 30 rutas agregadas, 5.575 viajes agregados, sin `data/demo`: OK.
