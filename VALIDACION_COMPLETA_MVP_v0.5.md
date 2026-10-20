# Informe de aceptación del MVP v0.5.0 — 19/10/2026

**Resultado final: NO APTO PARA PUBLICACIÓN DE RESULTADOS.** La capa técnica supera las comprobaciones disponibles, pero el MVP definido por producto NO puede validarse integralmente sin los datos reales completos y la comprobación visual/operativa en el sistema de destino.

## Evidencia técnica realmente ejecutada

- **63/63 pruebas unitarias y de regresión superadas**, desde una copia local del código.
- **13/13 controles HTTP y semánticos superados** a través de FastAPI TestClient sobre una base SQLite temporal vacía. Incluyen endpoints, corte histórico 18/10/2026, planificación desde 19/10, ausencia de valores falsos, y prohibición de aprobación con fuentes insuficientes.
- Arranque HTTP del servidor comprobado en Linux: `/api/version` devolvió `0.5.0`.
- Comprobación de la imagen visual automatizada con Chromium **no completada**: el navegador de este entorno no produjo captura. **No afirmar QA visual ni QA Windows.**
- `ACCEPTANCE_EVIDENCE.json` contiene la evidencia reproducible y `acceptance_run.py` repite las verificaciones.

## Correcciones respecto de v0.4.0

1. Fechas GTFS compactas inválidas ahora se validan con calendario real; `20261399` se rechaza.
2. Los segundos de los horarios GTFS se conservan hasta precisión de un segundo, en vez de truncarse silenciosamente a minutos.
3. Se rechazan identificadores vacíos o duplicados de rutas, paradas, expediciones y calendarios antes de importarlos.
4. Las secciones censales repetidas se rechazan para evitar inflar habitantes; coordenadas proyectadas tratadas erróneamente como WGS84 se rechazan.
5. Se añaden siete/ocho pruebas adversariales y un ejecutor de aceptación independiente de bases de datos existentes.

## Evidencia de adquisición de datos

Se intentaron acceder a: espejo GTFS actual Auif, CSV Eustat 2025, Transitland y Geofabrik. Las peticiones HTTPS fallaron por DNS/red restringida en este entorno; no se han recuperado ni incorporado datos oficiales. El método `container.download` sobre el CSV de Eustat tampoco completó la descarga.

Los archivos históricos de Transitland pueden requerir una clave autorizada o petición directa al NAP/operadores. **No tenemos autorización ni ficheros locales para certificar 656 jornadas (01/01/2025–18/10/2026) de cada operador.** Ninguna fecha se marca de modo ficticio como validada.

## Matriz de aceptación

| Área | Estado | Evidencia pendiente |
|---|---|---|
| ZIP y ejecución Python | **Verificado** | Instalar en Windows real |
| GTFS importador, calendario, excepciones | **Verificado con ensayo** | GTFS originales de ambos operadores |
| Fecha de corte histórico / planificación | **Verificado** | Contrastar planes con operador |
| Motor comparativo E↔OR/BI | **Verificado con ensayo** | Corredores y correspondencias de paradas reales |
| Datos históricos oficiales 2025–18/10/2026 | **Bloqueado** | Acceso e importación de versiones y contraste diario |
| Eustat + sección + edificios residenciales | **Bloqueado** | Descarga, normalización, correspondencia y totales verificados |
| Red peatonal OSM e isócronas de 10 minutos | **Verificado con ensayo** | Capa real, barreras, pendientes, validación de muestra |
| Población accesible / cobertura única | **Verificado con ensayo** | Población real y cotejo espacial |
| Seguridad remota / HTTPS | **Solo configuración de referencia** | Pruebas de despliegue y revisión de seguridad |
| Interfaz visual y accesibilidad en Windows | **No verificado** | Validación en navegador final |
| Publicación privada de análisis | **Bloqueada** | Todas las puertas anteriores y autorización final |

## Requisitos que NO se deben suavizar

- Territorio: Irun, Hondarribia, Errenteria, Pasaia, Lezo y Oiartzun.
- Operadores: Ekialdebus e Irunbus; histórico mensual desde enero 2025 hasta el **18/10/2026** para ambos.
- Lunes–jueves, viernes, sábado, domingo, excepciones de calendario, días festivos y nocturnos.
- Servicios desde el **19/10/2026** son **planificación**, incluso si el GTFS tiene validez posterior.
- Accesibilidad con red peatonal real de diez minutos, distribución residencial y población única sin doble conteo.
- Acceso privado, sin exportación inicial; ninguna publicación sin certificación histórica y GIS.

## Qué falta para una aceptación completa real

1. Obtener, mediante una fuente legítima, los ZIP históricos de **Ekialdebus** y **AUIF/Irunbus** que cubran cada fecha y los originales con hashes.
2. Obtener CSV Eustat 2025, geometrías censales GeoEuskadi, usos residenciales y red peatonal; ejecutar el cruce de **los seis municipios** y cotejar totales de población.
3. Auditar diferencias de la concesión de octubre 2026 y horarios, por operador, día y sentido, con evidencia documental.
4. Hacer control de calidad cartográfico con al menos una muestra representativa de paradas, pasos a nivel, ríos, pendientes y accesos.
5. Ejecutar toda la aplicación y pruebas de seguridad/usabilidad en un navegador de Windows de destino y aprobar el despliegue privado.

Los archivos históricos oficiales o las credenciales de archivo autorizado deben facilitarse por canal seguro, **no pegarse en conversaciones ni integrarse en el ZIP**. El MVP se mantiene en estado de validación parcial hasta entonces.
