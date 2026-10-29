# Preparación de publicación privada y criterios go/no-go

> **Actualización v1.3.0 (29/10/2026):** ver `VALIDACION_V1.3.0.md` y `OPERACION_LOCAL.md`. Código y datos se distribuyen por separado; esta entrega no se ha puesto en un servidor online.

## Situación actual

La aplicación está implementada, pero no se declara publicada ni certificada. El histórico GTFS se mantiene como artefacto separado del código. La release local incluye cartografía provincial, referencia Eustat y anclajes poblacionales verificables mediante manifiesto SHA-256.

## Puertas de calidad

1. **Cobertura temporal:** las jornadas del periodo histórico definido en el manifiesto, **por operador**, con versión adecuada y revisión documentada. Fechas posteriores al corte no forman parte del histórico.
2. **Calendario:** separar L–J, viernes, sábado y domingo; fechas excepcionales, festivos y servicios nocturnos; contrastar una muestra independiente de horarios publicados.
3. **Concesión octubre 2026:** revisión manual de equivalencias E → OR/BI, cambios de paradas, sentidos y variantes. La detección espacial es orientativa.
4. **Población:** tabla provincial Eustat 2025 reconciliada (88 municipios, 544 secciones y 724.797 habitantes); asignación a 85.948 anclajes del método v3, sin población sin asignar. Es una estimación no certificada.
5. **Geografía:** red peatonal conectada y validada, sin círculos; comprobar puentes, vados, barreras, cruces y pasos de peatones. Validar manualmente isócronas urbanas y rurales.
6. **Seguridad:** contraseña única larga, HTTPS, DNS, copias de seguridad, permisos del servidor, protección contra intentos de acceso y revisión de privacidad.
7. **Licencias:** atribución MITRAMS, Eustat, GeoEuskadi y OpenStreetMap conforme a condiciones específicas; verificar licencias de GTFS archivados.
8. **UX:** pruebas visuales reales en Windows y navegadores móviles, test de accesibilidad, manejo de errores y respuesta con base de datos real.
9. **Aprobación:** evaluación humana y acta de conformidad; la API jamás habilita la publicación por sí sola.

`python preflight.py --strict` genera un resumen y sale con error hasta completar las puertas de datos.

## Despliegue privado de referencia

1. Servidor con Docker Compose, dominio DNS y puertos 80/443 disponibles.
2. `cp .env.example .env`; configura `OBS_DOMAIN`, `OBS_ADMIN_USERNAME`, `OBS_ADMIN_PASSWORD`, `OBS_DATA_RELEASE_DIR` y `OBS_DATA_RELEASE`. Si la lectura no es pública, configura además `OBS_PUBLIC_READ=0`, `OBS_READER_USERNAME` y `OBS_READER_PASSWORD`. Nunca subas `.env` a repositorios.
3. Ejecuta `docker compose up -d --build`. Caddy tramitará HTTPS si el DNS y la accesibilidad exterior son correctos.
4. La lectura puede ser pública; la administración requiere otra credencial HTTP Basic. El acceso externo pasa por TLS y el proxy autorizado. No se publican puertos de la app directamente ni se importa sobre la release publicada.
5. Antes de exponer resultados a personas externas, importa datos reales, ejecuta `preflight.py --strict` dentro del contenedor (o desde el servidor) y completa la revisión humana.

**Antes de exponer el servicio:** probar el contenedor y proxy reales, restaurar una copia externa y configurar monitorización. El mapa usa un renderizador SVG local y cartografía raster GeoEuskadi/Esri; las peticiones de teselas llegan a esos proveedores. HTTP Basic es una solución mínima de administración, no un sistema avanzado de gestión de usuarios.

## Límites metodológicos actuales

- Las fuentes GTFS describen horarios **programados**, no autobuses observados ni puntualidad real.
- `frequencies.txt` con `exact_times=1` se expande determinísticamente conservando segundos. Las frecuencias sin horas exactas no se convierten en salidas ficticias y se rechazan explícitamente.
- La población censal se asigna a anclajes deterministas de la red peatonal y se deduplica entre paradas; el grosor visual no modifica el resultado.
- Isócronas: caminos conectados a partir de OSM con velocidad base de 4,5 km/h, topología de nodos, barreras, niveles y penalización de escaleras/superficies. No constituyen todavía un modelo universal de accesibilidad.
- Cobertura de frecuencias: se evalúa la mayor separación entre salidas, también desde el inicio y hasta el final de la franja seleccionada; líneas, sentidos y destinos permanecen separados.
- Scripts y estilos del visor son locales. El mapa base requiere conexión exterior a GeoEuskadi/Esri; las geometrías de transporte, red peatonal y población proceden de la release local.


## Controles v1.1.0

La auditoría incluye errores estructurales de cualquier GTFS utilizado para certificar días históricos y muestra las correspondencias de corredores como inferencias, no relaciones oficiales. El corte histórico está fijado a 18/10/2026. La API separa lectura y administración, los cálculos costosos usan un trabajador y el despliegue local inmutable expone únicamente `127.0.0.1:8873`. Se requiere validación de seguridad, licencias y datos reales antes de publicar resultados.
