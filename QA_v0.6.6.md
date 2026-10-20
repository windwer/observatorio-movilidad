# QA v0.6.6 · Revisión UX/UI y trazabilidad

## Cambios verificados

- El selector de línea usa `/api/routes`, un catálogo independiente del filtro de día, hora y línea. La opción seleccionada se conserva y las líneas sin servicio para el tipo de día aparecen identificadas, no desaparecen.
- La cartografía inicial usa el servicio oficial GeoEuskadi mediante una petición ArcGIS `export` por tesela. Si el servicio no responde, cada tesela puede caer de forma explícita a Esri World Topographic Map y la atribución visible cambia con el proveedor efectivo.
- La vista principal conserva la geometría GTFS, las paradas y las isócronas de red. La población Eustat se muestra como referencia territorial; la cobertura de una línea o parada solo se muestra como cifra cuando existen red peatonal, polígonos censales y edificios residenciales asignables.
- El KPI de fechas con fuente se retira de la fila principal. La trazabilidad pasa al panel de estado de consulta, junto con operador, línea, categoría de día, fuente temporal, jornadas disponibles y retrospectivas.
- La distribución temporal se sustituye por una cuadrícula compacta de jornadas con fuente. Las herramientas de población por frecuencia y cambios de paradas quedan agrupadas bajo un bloque avanzado cerrado para no ocupar la vista principal sin capas comparables.
- La versión se obtiene de `/api/version`; esta entrega es `0.6.6` y el lanzador, la API y la cabecera comparten esa versión.

## Comprobaciones ejecutadas

- `node --check static/app.js`
- `node --check static/offline_map.js`
- `python -m py_compile app.py engine.py launcher.py` usando el entorno Python del paquete histórico.
- `git diff --check`

## Límite metodológico explícito

El repositorio contiene la referencia tabular Eustat 2025 y la red peatonal OSM, pero no incorpora todavía polígonos censales ni edificios residenciales asignados. Por tanto, la interfaz no inventa población cubierta ni suma población parada a parada. Para activar esa cifra hay que importar ambas capas en GeoJSON y volver a ejecutar el cálculo espacial deduplicado.
