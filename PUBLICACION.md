# Preparación de publicación privada y criterios go/no-go

## Situación actual

La aplicación está implementada, pero no se declara publicada ni certificada.
No se incluyen GTFS ni capas geográficas reales en el ZIP. Para completar el histórico hay que recuperar sus versiones originales, unir población y censos y auditar los resultados.

## Puertas de calidad

1. **Cobertura temporal:** 656 jornadas (01/01/2025–18/10/2026) **por operador**, todas con versión adecuada y revisión documentada. Noviembre–diciembre 2026 y 19–31 octubre no forman parte del histórico.
2. **Calendario:** separar L–J, viernes, sábado y domingo; fechas excepcionales, festivos y servicios nocturnos; contrastar una muestra independiente de horarios publicados.
3. **Concesión octubre 2026:** revisión manual de equivalencias E → OR/BI, cambios de paradas, sentidos y variantes. La detección espacial es orientativa.
4. **Población:** tabla provincial Eustat 2025 reconciliada (88 municipios, 724.797 habitantes); geometría espacial y secciones con asignación residencial todavía limitadas a los seis municipios iniciales; sesgo por edificaciones `building=yes` investigado.
5. **Geografía:** red peatonal conectada y validada, sin círculos; comprobar puentes, vados, barreras, cruces y pasos de peatones. Validar manualmente isócronas urbanas y rurales.
6. **Seguridad:** contraseña única larga, HTTPS, DNS, copias de seguridad, permisos del servidor, protección contra intentos de acceso y revisión de privacidad.
7. **Licencias:** atribución MITRAMS, Eustat, GeoEuskadi y OpenStreetMap conforme a condiciones específicas; verificar licencias de GTFS archivados.
8. **UX:** pruebas visuales reales en Windows y navegadores móviles, test de accesibilidad, manejo de errores y respuesta con base de datos real.
9. **Aprobación:** evaluación humana y acta de conformidad; la API jamás habilita la publicación por sí sola.

`python preflight.py --strict` genera un resumen y sale con error hasta completar las puertas de datos.

## Despliegue privado de referencia

1. Servidor con Docker Compose, dominio DNS y puertos 80/443 disponibles.
2. `cp .env.example .env`; reemplaza `OBS_DOMAIN`, `OBS_USERNAME` y **la contraseña de ejemplo** por una credencial aleatoria y única. Nunca subas `.env` a repositorios.
3. Ejecuta `docker compose up -d --build`. Caddy tramitará HTTPS si el DNS y la accesibilidad exterior son correctos.
4. El servidor ejecuta la API con autenticación HTTP Basic, únicamente a través del proxy TLS. No se publican puertos de la app directamente.
5. Antes de exponer resultados a personas externas, importa datos reales, ejecuta `preflight.py --strict` dentro del contenedor (o desde el servidor) y completa la revisión humana.

**Seguridad adicional recomendada para un despliegue real:** VPN o allowlist IP; backups cifrados; TLS y renovación de certificados; limitación de intentos de login en el proxy; política de privacidad por teselas de OpenStreetMap y recursos externos (Leaflet y Google Fonts). HTTP Basic es una solución mínima para una beta privada, no un sistema avanzado de gestión de usuarios.

## Límites metodológicos actuales

- Las fuentes GTFS describen horarios **programados**, no autobuses observados ni puntualidad real.
- `frequencies.txt` no se expande: si está presente con registros, la importación se bloquea para evitar infravalorar la oferta.
- La población se asigna a edificios residenciales reconocidos; secciones sin edificios válidos quedan explícitamente sin asignar.
- Isócronas: caminos conectados a partir de OSM con velocidad base de 4,5 km/h, aproximación de acceso de 20 m. No representan un modelo detallado de pendientes ni accesibilidad universal.
- Cobertura de frecuencias: se evalúa la mayor separación entre salidas, también desde el inicio y hasta el final de la franja seleccionada; líneas, sentidos y destinos permanecen separados.
- La aplicación sirve hojas y scripts de Leaflet desde CDN y utiliza teselas OSM. Requiere conexión exterior para el mapa base mientras no se empaquete un proveedor local autorizado.


## Nuevos controles v0.4.0

La auditoría de publicación incluye ahora errores estructurales de cualquier GTFS utilizado para certificar días históricos, y muestra las correspondencias de corredores como inferencias, no relaciones oficiales. El corte histórico está fijado a 18/10/2026. Para ejecución local, utiliza `run_windows.bat` (puerto 8765 o siguiente libre); 8000 puede corresponder a una versión anterior. Se requiere validación de seguridad, licencias y datos reales antes de publicar resultados.
