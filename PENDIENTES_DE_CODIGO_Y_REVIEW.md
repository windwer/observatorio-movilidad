# Product review v0.6.0 — Estado funcional y deuda de producto

## Decisión del Product Manager pendiente
**No iniciar descargas de Transitland, Interline u otras APIs de datos antes de aprobación expresa.** La versión de demostración incorpora un almacenamiento independiente, desactiva escrituras por API y contiene solo GTFS e isócronas inventados; conserva el CSV oficial de población Eustat 2025 por separado.

## Lo que se puede validar ya
- Interfaz de mapa de dos operadores y selección de paradas y líneas.
- Filtros por año, mes y categorías lunes-jueves, viernes, sábado y domingo.
- Horarios programados de ejemplo, frecuencias, calendarios y excepciones, cambio de operador y sentido cuando existan en el GTFS.
- Comparador histórico 2025 vs 2026 y cambio de nombres E a OR/BI en datos ficticios.
- Corte fijo 18/10/2026, con planificación desde el 19/10/2026.
- Isócronas y población accesible con capa geográfica exclusivamente de demostración, y total real Eustat 2025 correctamente diferenciado.
- Seguridad de lectura de la demo: API de escritura y fuentes externas bloqueadas.

## Lo que falta a nivel de código / producto para cerrar el MVP
1. Validación visual manual en Windows y navegadores reales; se ha probado API y JavaScript, pero este entorno bloquea la navegación automatizada local.
2. Ajustar diseño, prioridades y navegación a las decisiones del Product Review, y comprobar accesibilidad y experiencia móvil.
3. E2E y seguridad del despliegue privado definitivo (TLS, autenticación, backups y permisos de usuarios).
4. Endurecer los flujos de ingestión de GTFS reales e historial sin cobertura; controlar calendarios excepcionales y casos raros, variantes y equivalencias de líneas divididas/fusionadas.
5. Ejecutar pipeline geográfico real y controlar sesgo residencial, nodos de acceso, límites municipales, red peatonal y calidad de isócronas con muestra manual.
6. Certificar la cobertura y procedencia del histórico de cada operador, comparativas con horarios oficiales y rendimientos reales con datos de tamaño completo.

## Conocemos la procedencia de los datos
- **Oficial**: total poblacional Eustat 2025 para seis municipios (150.832 personas, 109 secciones originales).
- **Ficticio**: posiciones de paradas, trazados, horarios, frecuencias, polígonos censales esquemáticos, edificios e isócronas de demostración.
- **Sin incorporar**: GTFS históricos certificados y cartografía GeoEuskadi/OSM real de seis municipios.

## Qué NO hacer
- No publicar estadísticas de oferta derivadas de la demo como reales.
- No utilizar la población accesible sintética como dato oficial.
- No introducir claves de API en variables front-end ni en el ZIP.

## Cómo iniciar review en Windows
Descomprime en carpeta nueva y ejecuta `run_product_review_windows.bat` (NO `run_windows.bat`). Abre la URL que indique la consola, por defecto http://127.0.0.1:8866/?v=0.6.0. Confirmar banner amarillo: **PRODUCT REVIEW · DEMOSTRACIÓN CON DATOS FICTICIOS**.
