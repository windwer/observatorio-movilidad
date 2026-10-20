# Integración Eustat 2025 — Datos reales

Fuente: https://es.eustat.eus/elementos/xls0011434_c.csv
Referencia: población de Gipuzkoa por distrito/sección, sexo, edad y nacionalidad al 01/01/2025.

## Realizado

- CSV oficial original adjuntado por el usuario, conservado sin alteración en `data/references/eustat_2025_original.csv`.
- Importación de población **por sección censal** a la SQLite incluida: tabla `population_sections`, con claves compuestas `municipality_code + district + section`.
- Extracción de los seis municipios acordados; eliminación de filas `Secc=000` porque son subtotales de distrito.
- Verificación independiente de los **12 subtotales de distrito**, que coinciden con sus secciones hijas.
- Resultado: **109 secciones**, **150.832 habitantes**: Bidasoaldea **77.625**, Oarsoaldea **73.207**.
- API `GET /api/population/status` y `GET /api/population/sections?municipality=Irun`.
- Panel nuevo en la aplicación con desglose municipal y comarcal; versión visible **0.5.1**.
- Hash de origen SHA-256: `600a0b87b7b5feb85c548c7c23bc0f517941f83b80ffafcf8a79d7d5482997f1`.
- CSV normalizado en `data/references/eustat_sections_2025_normalized.csv` y auditoría en `data/references/EUSTAT_2025_VALIDATION.json`.

| Municipio | Habitantes | Secciones |
|---|---:|---:|
| Irun | 60.665 | 42 |
| Hondarribia | 16.960 | 12 |
| Errenteria | 39.779 | 31 |
| Pasaia | 16.767 | 13 |
| Lezo | 6.188 | 4 |
| Oiartzun | 10.473 | 7 |
| **Total** | **150.832** | **109** |

## Importante: no confundir con cobertura espacial

Todavía **no** existe la geometría de las secciones en este paquete. Las coordenadas, áreas residenciales e isócronas caminando aún no están ligadas al CSV oficial. El panel territorial seguirá mostrando la accesibilidad como pendiente, evitando inventar datos de cobertura.

La siguiente entrada necesaria es el SHP/GeoJSON de **GeoEuskadi de secciones censales 2025** y, para distribución residencial, la capa de edificios residenciales. La unión se realizará usando municipio/distrito/sección; hay que verificar las claves reales del archivo antes de importarlo.

## Verificaciones

- Suite automatizada completa: 67 pruebas superadas (incluye 4 pruebas adicionales específicas del CSV real).
- Prueba de importación mediante API y relectura de las 42 secciones de Irun.
- Prueba negativa: alterar un subtotal oficial provoca rechazo y conserva el dataset anterior.
- No certifica el histórico de oferta GTFS ni la población cubierta por las paradas.
