> **Actualización v0.6.3:** ver [PRODUCT_REVIEW_MAPA_v0.6.3.md](PRODUCT_REVIEW_MAPA_v0.6.3.md) y [QA_v0.6.3.md](QA_v0.6.3.md) para red OSM, isócronas y población agregada por recorrido.

# Product review · Observatorio 0.6.1 (corrección bloqueante)

## Qué se ha corregido
- No se solicita **ninguna tesela** a OpenStreetMap ni otros proveedores. Mapa vectorial local con zoom, desplazamiento, selección de líneas y paradas. El mapa base es esquemático, no hay calles ni límites oficiales.
- Catálogo de DEMO completo para las líneas acordadas: **26 códigos E (2025), 25 OR/BI (desde octubre 2026), y 6 de Irunbus (L1-L4, G1-G2)**. Se preservan diferencias de periodo y días nocturnos.
- Geometrías, ubicación de las paradas DEMO, isócronas y todos los horarios de bus son **inventados para el test de producto**, no son el recorrido real.
- El único dato real demográfico es la población de Eustat 2025 (150.832 habitantes en seis municipios).

## Arranque Windows
1. Descomprime en **una carpeta nueva**.
2. Ejecuta `run_product_review_windows.bat`.
3. Accede a la dirección de la consola, normalmente `http://127.0.0.1:8866/?v=0.6.1`.
4. Comprueba la cabecera **DEMO v0.6.1**.

## Escenarios de aceptación
1. Octubre 2025 → Ekialdebus: 20 E diurnas + 6 nocturnas. Lunes-jueves muestran las 20 diurnas; viernes y sábado también nocturnas.
2. Octubre 2026 → Ekialdebus: 18 OR/BI diurnas + 7 nocturnas. Lunes-jueves muestran las 18 diurnas.
3. Irunbus: seleccionar L4 en cualquier mes y mostrar su trazado y paradas. Viernes/sábado permite revisar Gautxori.
4. Ver líneas de ambos operadores a la vez.
5. Hacer zoom con botones o rueda, arrastrar y seleccionar parada para horarios/isócrona.
6. Octubre 2026 muestra Histórico 1-18 y Planificación 19-31.

**No hay consultas automáticas a Transitland ni APIs de transporte. Esperamos al OK del Product Manager.**

**Importante:** el selector de líneas muestra el catálogo completo de cada periodo, incluso las nocturnas sin servicio para el tipo de día seleccionado. En tal caso las etiqueta claramente. El mapa representa las líneas que sí operan en la fecha seleccionada.
