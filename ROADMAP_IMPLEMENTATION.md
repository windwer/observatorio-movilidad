# Cierre de la hoja de ruta técnica · v1.1.0

Fecha de implementación: 24/10/2026. Alcance: preparación local; sin servidor online.

| Fase | Resultado implementado | Evidencia de aceptación |
|---|---|---|
| 1. Estabilización | Configuración y corte centralizados; Python 3.12 y dependencias exactas; CI funcional; lector/administrador separados; esquema migrado antes de servir; campos GTFS de agencia, modo, estación, accesibilidad y embarque; release de datos reproducible. | Tests de permisos, ingestión, calendario y build/validate/restore. |
| 2. Método espacial | Topología por nodos OSM, niveles, barreras y sentido peatonal; penalización de escaleras/superficies; origen virtual en tramo largo; 5/10 min por Dijkstra; población anclada a la red, deduplicada e independiente del dibujo; fallback híbrido por sección. | 544 secciones, 88 municipios, 724.797 habitantes, cero secciones sin asignar; regresiones de tramo largo y grosor visual. |
| 3. Servicio multiusuario | Cola persistente y trabajador separado; caché LRU acotada; timeout, cancelación y límite de trabajos; lecturas SQLite sin DDL; claves de resultado incluyen release y método; peticiones obsoletas del visor cancelables; límites de patrones explícitos. | Tests de cola/reutilización y script de 20 sesiones. |
| 4. Operación | Datos montados en modo inmutable; manifiesto SHA-256; restauración ensayable; salud/preparación separadas; métricas restringidas; contenedor no root, filesystem de solo lectura, límites CPU/RAM y perfil Compose sólo-local. | `data_release.py`, `/api/ready`, `/api/metrics`, Compose local y `scripts/load_test.py`. |

## Decisiones conscientes

- No se ha desplegado un servidor, por petición expresa. Caddy se mantiene en perfil `online-only`.
- No se migra todavía a PostgreSQL/PostGIS. Para una release SQLite inmutable y lectura moderada no es una condición técnica; sí lo será antes de introducir usuarios que escriban o administración concurrente.
- El histórico existente mantiene su estructura física para evitar una reescritura riesgosa de 2 GB. Las nuevas tablas separan identidad pública de línea y equivalencias por captura. La normalización total `feed_content/feed_snapshot` se reserva para la migración SQL; las capturas fechadas nunca deben eliminarse aunque compartan hash.
- La población es una estimación distribuida sobre la red peatonal. Está metodológicamente corregida respecto a la interpolación por área, pero sigue necesitando contraste humano antes de convertirse en indicador oficial.

## Puerta para la siguiente auditoría

## Evidencias de cierre local

- Release reproducible: `gipuzkoa-2026-10-24-v1.1.0`, 162 fuentes GTFS (80 Ekialdebus, 80 Irunbus, 1 Euskotren y 1 Errenteria urbano), manifiesto y cinco archivos verificados por SHA-256.
- Restauración independiente validada con 544 secciones censales, 88 municipios, 724.797 habitantes, 92.831 vías OSM y 85.737 anclajes residenciales; cero población sin asignar.
- Servicio restaurado e inmutable: `/api/ready` confirma base de datos, fuentes, censo, red y referencia poblacional; método `walk-network-anchors-v2`.
- Carga local: 20 sesiones durante 60 segundos, 2.254 respuestas, cero errores, latencia media 34,0 ms y p95 56,8 ms. Evidencia guardada como `outputs/runtime-v110/load-20-sessions.json` fuera del repositorio.
- Regresión completa: 85 pruebas superadas; tres suites DEMO heredadas omitidas al no existir sus fixtures en el checkout de producción.

## Puerta para la siguiente auditoría

La siguiente auditoría debe revisar el diff completo, observar memoria/arranque durante una ejecución prolongada y repetir la prueba de 20 sesiones durante 15 minutos. La aceptación online y las pruebas TLS públicas quedan fuera de esta entrega.
