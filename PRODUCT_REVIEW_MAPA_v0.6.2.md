# Product Review — Mapa cartográfico e isócronas (v0.6.2)

## Estado

**Implementado en código, pendiente de aceptación visual en el equipo del Product Manager.** Los datos de horarios, recorridos, paradas y calles peatonales de la demo son simulados. La base cartográfica se carga desde servicios reales: Esri World Topographic Map (por defecto) y GeoEuskadi (alternativo).

No se ha consultado la API de Transitland, ni se han usado las claves del usuario. El modo Product Review sigue bloqueando la descarga e importación de datos mediante la API de la aplicación.

## Cambios solicitados

**BUG-001. Mapa sin calles.** Sustituido el mapa esquemático por un visor geográfico de teselas reales, con dos proveedores alternativos y atribución. El error 403 del servidor voluntario de teselas OSM queda eliminado porque ya no se utiliza ese servicio.

**BUG-002. Isócronas de 5 y 10 minutos.** El backend acepta `minutes=5` y `minutes=10` de forma explícita; calcula dos áreas por la red peatonal; las geometrías se pintan superpuestas: naranja a 5 min, azul a 10 min. Cada capa se puede encender/apagar. La pantalla centra la parada escogida a una escala apropiada para apreciar ambas áreas.

## Procedimiento de revisión (Windows)

1. Descomprime en **una carpeta nueva**, por ejemplo `Observatorio_Review_062`.
2. Ejecuta `run_product_review_windows.bat`.
3. Abre la URL que te indique el iniciador (normalmente `http://127.0.0.1:8866/?v=0.6.2`). **No uses la pestaña vieja.**
4. Confirma que ves **DEMO v0.6.2** y el aviso de datos sintéticos.
5. Comprueba que el mapa tiene vías, edificios y topografía de Gipuzkoa oriental. Si falla, abre el desplegable «Mapa base» y elige **GeoEuskadi** o **Esri World Topographic Map**. Se necesita conexión a Internet para la cartografía real, no para el GTFS demo.
6. Verifica que se ven **5 minutos naranja** y **10 minutos azul**. Desactiva cada casilla para confirmar que las capas son independientes.
7. Haz clic en otra parada para centrarla y recalcular ambas áreas; utiliza **⌂** para volver a ver la red completa.
8. Filtra por Irunbus → L4 y Ekialdebus → BI05. Cambia el día y el mes y comprueba que siguen funcionando los filtros y la separación histórico/planificación del 18/10/2026.

## Límites deliberados del Product Review

- **Calles del mapa: reales y actuales, proporcionadas por el servicio cartográfico.** La cartografía requiere Internet, porque el ZIP no contiene teselas regionales licenciadas para uso local.
- **Recorridos, puntos de parada e isócronas: DEMO.** Las coordenadas y la red peatonal son de ensayo; un trazado recto de línea en la demo no debe interpretarse como itinerario oficial. Se sustituirá por `shapes.txt`, `stops.txt` y caminos oficiales/OSM después de tu OK.
- La validación automatizada en navegador está restringida en este entorno; no hay captura visual certificada en Windows.
- Si ambas fuentes externas fallan, el visor muestra un mensaje de error en vez de inventar un callejero.

## Criterios de aceptación

- CA-MAP-01: Base cartográfica real y legible (calles/topografía), al menos un proveedor accesible en tu navegador.
- CA-MAP-02: Zoom, desplazamiento y vuelta a vista completa funcionan.
- CA-MAP-03: Capas de líneas y paradas georreferenciadas permanecen alineadas al hacer zoom.
- CA-ISO-01: Dos áreas distintas y distinguibles (naranja 5 min, azul 10 min).
- CA-ISO-02: Activación independiente de las dos capas.
- CA-ISO-03: Seleccionar otra parada recalcula y centra las áreas correctamente.
- CA-DEMO-01: La aplicación advierte explícitamente que las líneas, paradas e isócronas son sintéticas.
- CA-DEMO-02: No se conecta con Transitland ni se expone una clave API.

**La aprobación sigue pendiente del Product Manager.**
