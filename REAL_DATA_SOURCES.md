# Datos reales incluidos · demo 0.6.5

Este paquete conserva la DEMO separada y arranca contra `data/real/observatorio_real.sqlite3`. No se conecta a Transitland ni descarga fuentes automáticamente: la base se ha construido con los dos ZIP entregados por el usuario.

## Instantáneas GTFS importadas

| Operador | Archivo entregado | Captura usada | Fechas GTFS | Rutas | Paradas | Viajes base | SHA-256 |
|---|---|---:|---|---:|---:|---:|---|
| Ekialdebus | `20261013_060005_Euskadi_ATTG_Lurraldebus_Ekialdebus.zip` | 2026-10-13 | 2026-10-12 → 2027-01-10 | 25 | 229 | 4.563 | `e1999c67ea17fc759190d5aa0835e52e71685936be6626c4a0b2cfe131bfd33a` |
| Irunbus / AUIF | `20261019_060137_Euskadi_ATTG_Lurraldebus_Auif_urb.zip` | 2026-10-19 | 2026-10-19 → 2027-01-17 | 5 | 77 | 1.012 | `8f8fe40cab6156d33cabe91114745d1b09df28bc666f138045253d650afb2d29` |

Los ZIP originales y las copias canónicas identificadas por hash se conservan en `data/real/originals/`. La fecha de captura es la del nombre del archivo entregado; la fecha de servicio procede de `calendar.txt` y `calendar_dates.txt`.

## Qué puede afirmarse

- Las líneas, paradas, shapes, calendarios y expediciones que muestra el visor proceden de estas instantáneas GTFS.
- Las cifras son oferta programada. La disponibilidad de un GTFS no demuestra que el servicio se prestara.
- La línea seleccionada puede mostrar longitud de `shape`, tiempo cabecera–última parada, velocidad comercial estimada y frecuencia por tipo de día.
- La línea seleccionada muestra también la primera y última salida, la amplitud de servicio y las expediciones con hora válida. Se pueden comparar dos fechas para distinguir más/menos horario de más/menos frecuencias.
- La red peatonal OSM se conserva para dibujar isócronas de red, no como un radio circular.
- **Eustat 2025:** la tabla oficial se conserva en `data/references/eustat_2025_original.csv`, está precargada en SQLite y se muestra como referencia visible en el visor: 109 secciones y 150.832 habitantes (Bidasoaldea 77.625; Oarsoaldea 73.207). Este total no se presenta como habitantes cubiertos por una isócrona.

## Qué queda bloqueado en esta fase

No se han incorporado polígonos censales ni edificios residenciales reales al paquete. Por tanto, la población cubierta por recorrido o por parada aparece como no calculable hasta cargar esas capas verificables. El CSV tabular Eustat 2025 sí está cargado como referencia oficial, pero no se utiliza para inventar población dentro de una isócrona.

## Arranque en Windows

Ejecuta `run_real_data_windows.bat`. La instancia real usa el puerto 8870 (o el siguiente libre), la base `data/real/observatorio_real.sqlite3` y `OBS_DEMO=0`. `run_product_review_windows.bat` sigue reservado a la DEMO sintética.

## Fuentes institucionales de referencia

- [NAP · conjunto de datos AUIF / Irunbus](https://nap.transportes.gob.es/ConjuntoDato/Detail/998)
- [Transitland · feed Ekialdebus](https://www.transit.land/feeds/f-lurraldebus~ekialdebus)
- [AUIF · red urbana de Irun](https://auif.es/)
- [Eustat · población por sección censal a 01/01/2025](https://es.eustat.eus/elementos/xls0011434_c.csv)
