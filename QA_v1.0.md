# QA v1.0 · población objetivo en isócronas

## Resultado

- Se incorporan las 544 geometrías oficiales de secciones censales 2025 del
  INE, unidas a los valores Eustat 2025 de toda Gipuzkoa (724.797 habitantes).
  La red peatonal OSM provincial contiene 92.831 vías y se utiliza como grafo
  real para alcanzar las secciones.
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

- `scripts/prepare_census_geometry.py`: 544 secciones y 724.797 habitantes.
- `python -m unittest -q test_territory.py`: 6 pruebas, OK.
- API local: `/api/geo/status` devuelve 544 secciones, 88 municipios,
  1.111.125 segmentos de grafo y `area_interpolation_ready: true`.
- API local: parada real `ekialdebus / 1 / 2026-10-21` devuelve 9.459
  habitantes a 5 minutos y 20.529 a 10 minutos.
- API local: línea real Ekialdebus devuelve población única deduplicada a 10
  minutos; no suma una sección más de una vez por sus paradas.
