# Correcciones del Product Review — v0.6.1

## Defectos reportados (19/10/2026)

1. **Bloqueante: teselas OpenStreetMap HTTP 403.** Eliminada totalmente la dependencia de teselas y de Leaflet desde CDN en modo Product Review. El mapa de revisión es ahora vectorial local, sin callejero oficial: zoom, panorámica, selección de recorrido, paradas, consulta de salidas e isócronas de demo.
2. **L4 ausente.** Incorporada al GTFS simulado de Irunbus y al selector, en 2025 y 2026. También G1 y G2.
3. **Ekialdebus incompleto.** La demo original contenía solo cuatro líneas por periodo. Se reconstruyó el catálogo ficticio de 2025 con 20 códigos diurnos E y 6 nocturnos; y el de octubre de 2026 con 18 códigos diurnos OR/BI y 7 nocturnos. Las líneas sin servicio en el tipo de día seleccionado figuran en el filtro, aunque no se dibujan en el mapa para esa fecha.
4. **Defecto hallado en prueba real:** rutas API demo registradas después del arranque bloqueante de Uvicorn. Corregido el orden de registro; `/api/demo/status` y `/api/demo/catalog` responden en el servidor real.

### Verificación
- 77 pruebas automáticas superadas.
- Nodo JavaScript: sintaxis verificada para ambos scripts.
- Servidor real: `/`, `/api/health`, `/api/demo/status`, `/api/demo/catalog`, `/api/map` L4 y `/static/offline_map.js` responden HTTP 200.
- Confirmado que no existe ninguna llamada a `tile.openstreetmap.org` en JS/HTML de la demo.
- Se mantiene la fecha de corte del 18/10/2026 y la separación entre histórico y planificación.

### Limitaciones explícitas
- El mapa base es una **vista geográfica esquemática offline**, con nombres y cuadrícula, NO calles ni cartografía oficial. Los puntos, trazados y datos de movilidad son todos ficticios y no sirven para investigación territorial.
- No se ha probado visualmente en Windows ni se han descargado GTFS oficiales. **El review continúa pendiente de tu aprobación.**
