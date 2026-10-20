# QA v1.0 · población objetivo en isócronas

## Resultado

- Se incorporan 109 geometrías oficiales de secciones censales de GeoEuskadi,
  unidas a los 109 valores de población Eustat 2025 (150.832 habitantes).
- La parada calcula población objetivo a 5 y 10 minutos mediante intersección
  de la isócrona de red con las secciones, con interpolación proporcional de
  superficie.
- La línea calcula población única a 10 minutos mediante la unión de las
  isócronas de sus paradas; no suma dos veces a la misma sección.
- Los edificios residenciales siguen siendo opcionales: si se incorporan, se
  utiliza la asignación dasimétrica por superficie y plantas.
- El resultado se etiqueta como estimación metodológica; no representa demanda
  observada ni acredita que el servicio se haya prestado.

## Comprobaciones ejecutadas

- `scripts/prepare_census_geometry.py`: 109 secciones y 150.832 habitantes.
- `python -m unittest -q test_territory.py`: 6 pruebas, OK.
- API local: `/api/geo/status` devuelve `area_interpolation_ready: true`.
- API local: parada de prueba `irunbus / 1502 / 2026-10-01` devuelve población
  estimada de 4.077 habitantes a 10 minutos.
- API local: línea de prueba `irunbus / route_id 1 / 2026-10-01` devuelve
  41.096 habitantes únicos a 10 minutos.
