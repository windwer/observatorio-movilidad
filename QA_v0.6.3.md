# QA v0.6.4

## Verificación automatizada

- Red empaquetada: 11.400 vías OSM, licencia ODbL y `transport_api_used: false`.
- Irun centro: 5 min = 615 nodos / 11.356 m de red; 10 min = 2.687 nodos / 46.564 m.
- Geometrías válidas, orgánicas y anidadas: 5 min está dentro de 10 min.
- Irunbus L1: 4 paradas conectadas; cobertura única estimada a 10 min: 8.400 habitantes en la demo.
- La unidad residencial se cuenta una sola vez aunque la cubran varias paradas.

## QA manual pendiente de navegador

- Cargar la URL nueva del iniciador, no una pestaña antigua.
- Cambiar Irunbus L1 → L2 y verificar que el KPI cambia de recorrido.
- Desmarcar 5/10 min y confirmar independencia visual.
- Cambiar de parada y confirmar que el texto de parada cambia sin perder el KPI agregado.
- Probar GeoEuskadi y Esri; ambas teselas requieren Internet.

La captura adjunta del Product Review mostraba el fallo de KPI 0; esta versión lo corrige conectando automáticamente `/api/geo/network?route_id=...` tras pintar el mapa.

El punto de parada usa ahora un radio cartográfico reducido; la tarjeta separa **Cobertura del recorrido** de **Cobertura de la parada** (5/10 min).
