# Validación técnica y estado de adquisición · v0.3.0

Fecha de corte formal: **18 de octubre de 2026**. La versión está destinada a uso **privado y local**.

## Pruebas realizadas en entorno de construcción

- **34 pruebas automatizadas superadas en fase de desarrollo** (`python -m unittest discover -s tests -v`).
- Código JavaScript validado sintácticamente con `node --check static/app.js`.
- API FastAPI arrancó y respondió a `GET /api/health` con `cutoff=2026-10-18` y `published=false`.
- Prueba HTTP de importación GTFS real **a partir de una muestra sintética generada para pruebas**, consulta mensual, mapa y horario de parada.
- Pruebas geométricas sobre una red peatonal artificial: límite de recorrido, edificios residenciales dentro/fuera de cobertura, ausencia de red conectada, persistencia y no doble conteo de población.
- **La prueba automatizada de navegador no pudo completarse:** el entorno de navegación devuelve `net::ERR_BLOCKED_BY_ADMINISTRATOR` al acceder al servidor local. No se certifica experiencia visual en Windows/macOS.
- **No se validó ejecución en Windows**. El instalador usa entorno virtual y está preparado, pero requiere una prueba en dicho sistema.

## Descarga de fuentes intentada

| Fuente | Resultado |
|---|---|
| Ekialdebus GTFS actual (NAP/Transitland mirror) | Falló: DNS de este entorno |
| Irunbus GTFS actual (NAP/Transitland mirror) | Falló: DNS de este entorno |
| Eustat CSV secciones censales 2025 | Falló: DNS de este entorno |
| GeoEuskadi SHP de secciones | Falló: DNS de este entorno |
| OSM red y edificios por Overpass | No ejecutada aquí: red externa bloqueada; código instalado para ejecución local |

**Esto no demuestra indisponibilidad de las fuentes.** El usuario dispone del botón «Obtener datos oficiales» y del iniciador `run_bootstrap_windows.bat` para intentar descargarlas desde su propio equipo.

## Lo que falta para considerar COMPLETO el MVP

1. Recuperar y validar las versiones GTFS que cubren todas las fechas del **01/01/2025 al 18/10/2026** para ambos operadores.
2. Confirmar los cambios de las líneas E a OR/BI por parada, corredor y horarios oficiales.
3. Cruzar los datos de población de Eustat con la cartografía GeoEuskadi sobre claves censales reales y cargar la capa resultante.
4. Descargar y validar la red peatonal y los edificios residenciales OSM y contrastar accesos a paradas y sesgos de asignación.
5. Calcular y revisar las cifras reales de cobertura poblacional de ambas comarcas, con incertidumbre y limitaciones.
6. Certificar las reglas de calidad y realizar una prueba de aceptación visual en Windows.

**No se han introducido horarios, poblaciones o coberturas inventadas.** El histórico programado es diferente del servicio realmente realizado. La fecha de corte histórico no avanza automáticamente.


## Cambios desde v0.2

- Auditoría de fuente histórica por fecha; publicación denegada sin revisiones verificables.
- Comparación espacial de paradas y población por frecuencia.
- Importación de histórico con credenciales autorizadas y verificación de hash.
- Controles de origen HTTP, cabeceras de seguridad y despliegue de ejemplo en HTTPS.
- Corrección de segmentos peatonales largos.
- Bloqueo preventivo de GTFS con `frequencies.txt` cuando la expansión no está implementada.

**La imposibilidad de descargar archivos externos en este entorno continúa.** Las descargas remotas no están verificadas end-to-end aquí; las rutas API y el procesamiento se prueban localmente con datos GTFS y geometrías artificiales claramente identificadas como fixtures.
