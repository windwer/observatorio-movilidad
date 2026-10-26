# Segunda auditoría técnica · v1.1.0

Fecha de cierre: 26 de octubre de 2026.

## Dictamen

**GO técnico para etiquetar `v1.1.0`, sujeto a que el mismo commit termine en
verde en CI antes de publicar la etiqueta remota.**

La aplicación es apta para continuar hacia una preproducción controlada. No se han
encontrado defectos P0 o P1 abiertos en código, integridad de datos, cálculo de
cobertura, seguridad básica o ejecución local. Este dictamen no certifica que los
horarios GTFS equivalgan a servicio realmente prestado ni autoriza por sí solo la
publicación de conclusiones históricas.

## Alcance revisado

- API FastAPI, motor GTFS, trabajos asíncronos y persistencia SQLite.
- Cálculo peatonal por red OSM y asignación poblacional Eustat 2025.
- Cliente web, selector de líneas, mapa, indicadores y estados de carga.
- Configuración, secretos, autenticación, límites de petición y modo inmutable.
- Imagen Docker, Compose, proxy Caddy, health/readiness y ejecución de worker.
- Release reproducible, pruebas automatizadas, carga concurrente y CI.

## Evidencias de aceptación

- 85 pruebas ejecutadas correctamente; 3 pruebas DEMO heredadas omitidas de forma
  explícita.
- Sintaxis Python y JavaScript válida; `pip check` sin dependencias rotas.
- Release `gipuzkoa-2026-10-24-v1.1.0` validada con 162 feeds y cero errores de
  claves foráneas.
- Población: 724.797 habitantes, 544 secciones, 88 municipios y 85.737 anclajes
  poblacionales, sin población no asignada.
- Red peatonal: 92.831 geometrías OSM provinciales.
- Prueba funcional BI05: 35/35 paradas conectadas y 46.468 habitantes únicos
  estimados a diez minutos.
- Selector de línea corregido para conservar el catálogo independiente del filtro
  de línea seleccionado.
- Prueba sostenida superada: 20 sesiones concurrentes durante 1.557 segundos,
  12.088 peticiones, cero errores, 56,0 ms de media y p95 de 44,9 ms frente al
  presupuesto de 1.000 ms.

## Arquitectura resultante

1. El proceso web sirve consultas y encola análisis pesados.
2. Un worker independiente reclama y ejecuta trabajos durables desde una base de
   estado separada.
3. La base GTFS y la cartografía se publican como release inmutable, montada en
   solo lectura y verificada mediante manifiesto y SHA-256.
4. El cálculo de isócronas recorre la topología peatonal OSM mediante Dijkstra; la
   población se deduplica con anclajes censales versionados.
5. Caddy termina TLS y el despliegue Compose aplica límites de CPU/memoria,
   filesystem de solo lectura, healthcheck y red privada.
6. CI valida dependencias, sintaxis, regresiones, catálogo, población provincial y
   la composición del despliegue.

## Riesgos residuales no bloqueantes

- Las llamadas obsoletas `shapely.ops.transform` generan avisos; deben migrarse
  antes de una futura actualización mayor de Shapely.
- SQLite es adecuado para esta fase y una carga analítica moderada. Para escritura
  concurrente multiusuario o varios nodos será necesario migrar estado y datos a
  PostgreSQL/PostGIS y usar una cola externa.
- Docker Compose se valida en CI porque Docker no está instalado en la máquina de
  auditoría local.
- Antes de una web pública siguen siendo obligatorios: dominio/TLS real, copias de
  seguridad ensayadas, observabilidad externa, política de privacidad, análisis de
  vulnerabilidades y prueba de restauración en el entorno de destino.

## Puerta de publicación

La etiqueta técnica no elimina la advertencia funcional: los GTFS describen
oferta programada. Cualquier afirmación sobre servicio prestado, mejora histórica
o cobertura oficial necesita una validación metodológica y de fuente separada.
