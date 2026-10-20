# Observatorio v0.4.0 — Informe de entrega y publicación

**Fecha histórica de referencia fija:** 18 de octubre de 2026. **Destinatarios:** entorno privado de análisis. **Estado:** NO APTO PARA PUBLICACIÓN DE RESULTADOS.

## Software implementado

Interfaz 0.4.0, superposición de Ekialdebus e Irunbus en mapa con advertencia de fuentes faltantes, arranque local sin conflicto con v0.1.1, importación GTFS, selección diaria/mensual, calendarios y excepciones, planificación posterior al 18/10, diferencia de paradas y corredores, análisis de horarios, isócronas 10 minutos, estimación demográfica residencial, cobertura sin duplicación, auditoría GTFS, puerta de publicación, scripts de adquisición/importación histórica y despliegue privado de referencia.

## Datos pendientes de conseguir y verificar

- Histórico GTFS completo Ekialdebus y AUIF/Irunbus 2025–18/10/2026, con versiones fechadas y permisos de acceso a los ZIP históricos. Transitland documenta acceso limitado a archivos históricos.
- Horarios y modificaciones históricas contrastados con fuentes de operadores; ningún documento ha sido auditado y firmado por una persona responsable.
- Secciones geográficas + población Eustat cruzadas usando los campos reales de GeoEuskadi; edificios residenciales y red peatonal importados y validados en los seis municipios.
- Verificación de cambios tras la nueva concesión de octubre de 2026, incluyendo variantes, fusiones y transbordos; el emparejamiento espacial automático es únicamente una propuesta.
- Seguridad de despliegue real, licencias, accesibilidad y QA visual sobre Windows con los datos integrados.

## Límites metodológicos

La fuente GTFS describe servicio **programado**, no necesariamente ejecutado. Los datos desde 19/10/2026 son **planificación**. La población asignada a edificios es una **estimación** condicionada por la calidad de edificios, entradas, red peatonal y secciones censales; no describe demanda real. En ventanas horarias estrechas, la prueba de frecuencia usa separaciones máximas incluyendo bordes y requiere al menos dos salidas. Fuentes incompletas nunca producen comparativas numéricas aparentes.

## Verificación técnica

**Resultados de validación (19/10/2026):**
- **55/55 pruebas automatizadas superadas** desde la carpeta de fuentes y desde una copia recién descomprimida del ZIP.
- Código JavaScript `static/app.js` comprobado con `node --check` sin errores sintácticos.
- ZIP validado íntegramente, sin errores de descompresión y sin bases de datos de ensayo empaquetadas.
- Servidor arrancado desde copia limpia, `HTTP 200` y versión **0.4.0** en `/api/health`, cabecera HTML verificada, `Cache-Control: no-store` y corte histórico correcto.
- Auditoría `/api/audit/readiness` devuelve **NO PUBLICAR** al faltar fuentes; `/api/quality` informa correctamente de cero versiones, sin inventar datos.
- Intentos de descarga de GTFS, Eustat y OSM bloqueados en este entorno por resolución DNS; no se han extraído históricos.
- La automatización visual Chromium recibió `ERR_BLOCKED_BY_ADMINISTRATOR` incluso al entrar al servidor local. **UI visual y Windows real aún no certificados.**

## Pasos para levantar los bloqueos

1. Ejecutar `run_full_setup_windows.bat` y revisar `data/full_setup_report.json`.
2. Aportar al importador las versiones históricas de ambos operadores (con una clave de archivo autorizada o los ZIP oficiales).
3. Ejecutar `normalize_eustat.py`, inspeccionar el SHP y configurar el cruce geográfico con códigos completos de municipio, distrito y sección.
4. Importar caminos, edificios y sección-población; validar cobertura territorial y errores de asignación.
5. Auditar los horarios diarios y contrastar las diferencias 2025–2026 contra fuentes oficiales.
6. Ejecutar `preflight.py --strict`, validar seguridad y UX en el servidor privado y autorizar la publicación.

**No se ha desplegado ni publicado automáticamente el proyecto.**
