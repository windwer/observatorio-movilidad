# Integración Eustat 2025 — Datos reales

Fuente: https://es.eustat.eus/elementos/xls0011434_c.csv
Referencia: población de Gipuzkoa por distrito/sección, sexo, edad y nacionalidad al 01/01/2025.

## Realizado

- CSV oficial original adjuntado por el usuario, conservado sin alteración en `data/references/eustat_2025_original.csv`.
- Importación de población **por sección censal** a la SQLite incluida: tabla `population_sections`, con claves compuestas `municipality_code + district + section`.
- Carga de los **88 municipios de Gipuzkoa**; eliminación de filas `Secc=000` porque son subtotales de distrito.
- Verificación independiente de los **120 subtotales de distrito**, que coinciden con sus secciones hijas.
- Resultado: **544 secciones**, **724.797 habitantes**: Bidasoaldea **77.625**, Oarsoaldea **73.207** y resto de Gipuzkoa **573.965**.
- API `GET /api/population/status` y `GET /api/population/sections?municipality=Irun`.
- Panel nuevo en la aplicación con desglose municipal y comarcal; versión visible **1.0**.
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
| **Total Gipuzkoa** | **724.797** | **544** |

## Cobertura espacial provincial

La geometría censal 2025 ya está unida a las 544 secciones Eustat de Gipuzkoa
mediante la capa oficial **INE Secciones_2025**. La red peatonal provincial se
descarga desde OpenStreetMap por teselas y se filtra por accesibilidad a pie.
Las isócronas calculan el alcance por Dijkstra sobre esa red y dibujan sólo la
unión de los tramos alcanzables; la población se estima por intersección de área
de sección y no se presenta como demanda observada.

## Verificaciones

- Suite automatizada completa: 67 pruebas superadas (incluye 4 pruebas adicionales específicas del CSV real).
- Prueba de importación mediante API y relectura de las 42 secciones de Irun.
- Prueba negativa: alterar un subtotal oficial provoca rechazo y conserva el dataset anterior.
- No certifica el histórico de oferta GTFS ni la población cubierta por las paradas.
