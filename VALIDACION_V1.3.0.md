# Correcciones y validación · 29/10/2026

## Estado de entrega

Código preparado como v1.3.0 y datos reconstruidos con
`walk-network-anchors-v3`. Ejecución exclusivamente local. El usuario ha
autorizado publicar estos cambios en GitHub manteniendo las validaciones
pendientes documentadas. No se ha desplegado el visor en un servidor online.

La batería completa ejecutó **104 pruebas, sin fallos, con 3 omitidas** por
fixtures DEMO antiguos ausentes. Una comprobación posterior de **34 pruebas
unitarias** terminó sin fallos, con una omitida por la restricción local del
bucle asíncrono de Windows. Una prueba adicional con procesos reales verificó
caducidad, cancelación, recuperación y rechazo de trabajos de datos anteriores.
Las **7 pruebas Node de interfaz** pasan, al igual
que la comprobación de sintaxis y `pip check`.

La repetición final de carga está **pendiente**: la revisión automática no
pudo autorizarla porque se agotó el límite de uso de herramientas. No se
considera aprobada ni se sustituyen sus resultados por las pruebas unitarias.
Docker no está instalado en este equipo: se añadió un ensayo en CI, pero no
se declara ejecutado el contenedor ni el proxy HTTPS de esta versión.
La prueba del cargador geográfico fuera del hilo asíncrono permanece disponible
para CI; no se ha validado localmente porque el bucle de Windows crea una
conexión interna que este entorno restringe.

## Hallazgos corregidos

| Área | Cambio y evidencia |
|---|---|
| Circuitos peatonales | Se conservan los tramos de caminos cerrados; prueba de 500 m frente a los 100 m que antes quedaban. |
| Sentidos únicos | El origen, recorrido y destino respetan `oneway:foot`, también en dirección inversa; regresiones específicas. |
| Población | Anclajes reconstruidos y vinculados a las huellas de sus archivos de origen; se conserva el total censal y no se suma dos veces una unidad. |
| Identificadores del mapa | El identificador visual lleva operador; el ID enviado al GTFS conserva su valor original. Prueba del mapa combinado. |
| Cola | Reserva y límite de trabajos en una transacción; deduplicación concurrente, latidos, renovación y rechazo de resultados caducados. |
| Cancelación y tiempo límite | Proceso de cálculo separable y terminable; prueba con procesos reales que verifica recuperación tras ambos casos. |
| Cálculos costosos | Cobertura, frecuencia y diferencias usan la cola. Una parada sin precálculo devuelve `202`; su petición no construye el grafo web. |
| Importación | Parseo GTFS/CSV y construcción geográfica fuera del bucle de peticiones asíncronas; cargas separadas de la release publicada. |
| Actualización de datos | Staging, construcción, validación, precálculo, activación coordinada y vuelta a la versión anterior mediante CLI. |
| Cachés y memoria | Identidad de datos/método/perfil, rechazo de anclajes antiguos, eliminación de bloqueos tras errores y retención de resultados. |
| Observabilidad | Latido por identidad de datos, disponibilidad del trabajador en readiness, rutas de métricas agrupadas y rotación de registros en Compose. |
| Acceso web | Hosts autorizados, origen de escrituras, credenciales de lectura/administración separadas y proxy privado explícito. |
| Evolución | Catálogo configurable, comparación con años seleccionables y auditoría mensual sin limitarse a 2025/2026. |
| Mapa base | Teselas cacheadas GeoEuskadi en lugar de exportación dinámica: el servicio devolvía PNG válidos pero vacíos. Tesela oficial inspeccionada visualmente. |
| Interfaz | Catálogo conservado al seleccionar línea, controles de carga ocultos en lectura, administración vacía oculta y versión correcta en cabecera. |
| Dependencias | Restricciones de versiones transitivas, auditoría sin vulnerabilidades conocidas y comprobación periódica preparada en CI. |

## Pruebas con datos reales

La release conserva **162 capturas GTFS**, población de **724.797 habitantes**,
**544 secciones** y **88 municipios**. Los anclajes del método corregido son
**85.948**, sin población sin asignar. Se precalcularon **968 coordenadas de
parada**, a 5 y 10 minutos; la preparación completa registró 1.279,5 segundos.

El ensayo HTTP verificó las cuatro redes cargadas, mapa combinado, una
cancelación real, reutilización de resultados, comparaciones y cobertura por
nivel de servicio. Ejemplo observado en la fecha 22/10/2026:

| Caso | Resultado estimado |
|---|---:|
| Irunbus, ID GTFS de línea `1`, 32 paradas conectadas | 42.172 habitantes únicos a 10 min |
| Parada de esa línea, 5 min | 3.602 habitantes |
| Misma parada, 10 min | 15.049 habitantes |

Los polígonos de esa comprobación fueron válidos y el de 5 minutos quedó
contenido en el de 10. En navegador se seleccionó BI05: el catálogo mantuvo
59 opciones y mostró 45.893 habitantes únicos de línea, junto al detalle
poblacional de la parada. No se observaron errores en la consola consultada.

Se generó y restauró una copia real de la base, cartografía, referencia y
estado SQLite, verificando sus huellas. También se probaron rechazo de
manifiestos alterados y protección contra escritura sobre una release.

## Rendimiento: resultado que permanece abierto

La primera carga mixta de 20 sesiones hizo 545 peticiones y detectó 17
errores de espera en una parada aún no preparada. Eso motivó la corrección
del cálculo de parada sin precálculo: ahora se encola, con regresión unitaria
que prohíbe cargar el grafo en esa petición. Falta repetir la medición HTTP
después de esa corrección. No hay un p95 final aprobado para v1.3.0.

## Límites y salida a web

- La población cubierta es una estimación censal distribuida sobre la red;
  no se dispone de distribución residencial exhaustiva ni de demanda observada.
- La red depende de la integridad de OSM. Velocidad de 4,5 km/h y penalizaciones
  no sustituyen una validación de campo ni modelan todas las discapacidades.
- Antes de exponerla faltan la carga final HTTP, ensayo real Docker/Caddy,
  HTTPS, monitorización del servidor y una copia fuera de este dispositivo.
- Las revisiones documentales de horarios y licencias siguen siendo humanas;
  que las pruebas del software pasen no certifica el servicio prestado.

Procedimiento de operación: [OPERACION_LOCAL.md](OPERACION_LOCAL.md).
