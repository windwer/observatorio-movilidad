# Datos reales incluidos · aplicación 1.0

Este paquete conserva la DEMO separada y arranca contra `data/real/observatorio_real.sqlite3`. No se conecta a Transitland ni descarga fuentes automáticamente: la base histórica se ha construido con los ZIP entregados por el usuario y la ampliación de redes usa las publicaciones GTFS estáticas oficiales de Moveuskadi.

## Instantáneas GTFS importadas

| Operador | Archivo entregado | Captura usada | Fechas GTFS | Rutas | Paradas | Viajes base | SHA-256 |
|---|---|---:|---|---:|---:|---:|---|
| Ekialdebus | `20261013_060005_Euskadi_ATTG_Lurraldebus_Ekialdebus.zip` | 2026-10-13 | 2026-10-12 → 2027-01-10 | 25 | 229 | 4.563 | `e1999c67ea17fc759190d5aa0835e52e71685936be6626c4a0b2cfe131bfd33a` |
| Irunbus / AUIF | `20261019_060137_Euskadi_ATTG_Lurraldebus_Auif_urb.zip` | 2026-10-19 | 2026-10-19 → 2027-01-17 | 5 | 77 | 1.012 | `8f8fe40cab6156d33cabe91114745d1b09df28bc666f138045253d650afb2d29` |
| Euskotren (tren, E1/E2) | `gtfs_euskotren.zip` | 2026-10-21 | 2026-10-21 → 2026-11-30 | 2 | 103 | 3.569 | `79f1940b9eccc1bf001628a10e0e1c702a9fb328fac97648eb7129614ef16150` |
| Errenteria bus urbano | `gtfs_errenteriako_urbanoa.zip` | 2026-10-21 | 2026-10-19 → 2026-12-31 | 9 | 82 | 293 | `3dfe97d2de370fdd9beace423d4011724a9bacd893218a662596624c1bfc7168` |

Los ZIP originales y las copias canónicas identificadas por hash se conservan en `data/real/originals/`. La fecha de captura es la del nombre del archivo entregado o de la descarga oficial; la fecha de servicio procede de `calendar.txt` y `calendar_dates.txt`. El feed Euskotren publicado por Moveuskadi también contiene tranvías y funicular: la ingesta conserva únicamente E1 y E2 para no presentar otros modos como tren dentro de este ámbito.

## Qué puede afirmarse

- Las líneas, paradas, shapes, calendarios y expediciones que muestra el visor proceden de estas instantáneas GTFS.
- Las fuentes actuales de Euskotren y Errenteria se consultan por sus URLs estáticas oficiales de Moveuskadi; no se activa ninguna API de Transitland.
- Las cifras son oferta programada. La disponibilidad de un GTFS no demuestra que el servicio se prestara.
- La línea seleccionada puede mostrar longitud de `shape`, tiempo cabecera–última parada, velocidad comercial estimada y frecuencia por tipo de día.
- La línea seleccionada muestra también la primera y última salida, la amplitud de servicio y las expediciones con hora válida. Se pueden comparar dos fechas para distinguir más/menos horario de más/menos frecuencias.
- La red peatonal OSM se conserva para dibujar isócronas de red, no como un radio circular.
- **Eustat 2025:** la tabla oficial se conserva en `data/references/eustat_2025_original.csv`, está precargada en SQLite y se muestra como referencia visible en el visor: 109 secciones y 150.832 habitantes (Bidasoaldea 77.625; Oarsoaldea 73.207). La geometría oficial de esas secciones se conserva en `data/real/geography/census.geojson` y permite estimar la población objetivo dentro de cada isócrona.

## Qué queda bloqueado en esta fase

La estimación base utiliza intersección proporcional entre la isócrona de red y las secciones Eustat 2025, deduplicando la población entre paradas para la línea. Los edificios residenciales no están incluidos todavía; si se cargan, sustituyen la interpolación de sección por una asignación dasimétrica más precisa. El resultado se etiqueta siempre como estimación y no como demanda observada.

## Arranque en Windows

Ejecuta `run_real_data_windows.bat`. La instancia real usa el puerto 8870 (o el siguiente libre), la base `data/real/observatorio_real.sqlite3` y `OBS_DEMO=0`. `run_product_review_windows.bat` sigue reservado a la DEMO sintética.

## Fuentes institucionales de referencia

- [NAP · conjunto de datos AUIF / Irunbus](https://nap.transportes.gob.es/ConjuntoDato/Detail/998)
- [Transitland · feed Ekialdebus](https://www.transit.land/feeds/f-lurraldebus~ekialdebus)
- [Moveuskadi · índice oficial de datos GTFS](https://www.euskadi.eus/contenidos/ds_movilidad/md_ideeu_moveuskadi/es_def/index.shtml)
- [Moveuskadi · GTFS Euskotren](https://opendata.euskadi.eus/transport/moveuskadi/euskotren/gtfs_euskotren.zip)
- [Moveuskadi · GTFS Errenteria urbano](https://opendata.euskadi.eus/transport/moveuskadi/errenteria/gtfs_errenteriako_urbanoa.zip)
- [AUIF · red urbana de Irun](https://auif.es/)
- [Eustat · población por sección censal a 01/01/2025](https://es.eustat.eus/elementos/xls0011434_c.csv)
