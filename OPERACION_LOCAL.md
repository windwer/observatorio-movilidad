# Operación local y actualización de datos · v1.3.0

El visor consulta una release inmutable. Las cargas se hacen en otra carpeta;
la base publicada nunca se abre para escritura. No se ha desplegado en Internet.

## Preparar una carga

1. `python release_manager.py stage RUTA_RELEASE RUTA_STAGING` crea una copia
   verificada y editable, sin modificar la release original.
2. Importa el manifiesto histórico contra esa copia:
   `python import_sources.py --manifest MANIFIESTO.json --db RUTA_STAGING/observatorio_real.sqlite3`.
   Cada entrada conserva operador, fecha de captura, nombre y huella del ZIP.
   Para cargar geografía o CSV con la interfaz administrativa, arranca una
   instancia separada en localhost con `OBS_DB`, `OBS_GEOGRAPHY_DIR` y
   `OBS_REFERENCE_CSV` apuntando a staging y `OBS_IMMUTABLE_DATA=0`.
3. Para añadir operadores, proporciona `OBS_CATALOG_FILE` con un JSON que
   asocie códigos a `label`, `mode` y, opcionalmente, `route_names`.
   Ejemplo: `{"nuevo_bus":{"label":"Nuevo operador","mode":"bus"}}`.
   Define el catálogo antes de importar y construir la nueva release.
4. Detén las cargas de staging antes de construir. El constructor hace una
   copia SQLite consistente y rechaza una cartografía que cambie durante la copia.

## Construir, precalcular y activar

```text
python data_release.py build --db RUTA_STAGING/observatorio_real.sqlite3 --geography RUTA_STAGING/geography --reference RUTA_STAGING/references/eustat_2025_original.csv --output NUEVA_RELEASE --release-id IDENTIFICADOR_UNICO
python scripts/prepare_accessibility.py --db NUEVA_RELEASE/observatorio_real.sqlite3 --geography NUEVA_RELEASE/geography --cache RUNTIME/access-cache.sqlite3
python data_release.py validate NUEVA_RELEASE
python release_manager.py activate NUEVA_RELEASE RUNTIME/active.json --state-db RUNTIME/state.sqlite3
python release_manager.py serve RUNTIME/active.json --port 8874
```

`serve` ejecuta web y trabajador juntos. Cuando cambia el puntero de activación,
reinicia ambos y comprueba datos y latido del trabajador. Si una actualización
no supera ese arranque, vuelve al puntero anterior. Hay una breve interrupción;
no es un despliegue sin parada. Mantén una única instancia del supervisor.

Para volver manualmente: `python release_manager.py rollback RUNTIME/active.json`.
El catálogo, corte temporal, comienzo del histórico, perfil peatonal y método
quedan dentro del manifiesto. Los resultados anteriores no se reutilizan si
cambia la identidad de datos, geografía o método.

## Copias y recuperación

```text
python release_manager.py backup RUTA_RELEASE RUTA_BACKUP --state-db RUNTIME/state.sqlite3
python release_manager.py restore-backup RUTA_BACKUP NUEVO_DESTINO
```

La copia usa la API de backup SQLite para el estado, verifica la release y
conserva huellas de los archivos. La recuperación rechaza huellas incorrectas.
Los destinos deben ser nuevos. Conserva aparte los ZIP GTFS originales y una
copia en otro dispositivo; una copia en el mismo disco no cubre su avería.

## Comprobaciones

- `/internal/health`: proceso web vivo, sin requerir credenciales de lector.
- `/api/ready`: datos y población listos; `analysis_ready` y `checks.worker`
  indican si el trabajador correspondiente a esos datos está operativo.
- `python worker.py --healthcheck`: comprueba el latido y la identidad de datos.
- `/api/metrics`: acceso administrativo; agrupa las rutas sin crear una serie
  distinta para cada identificador de trabajo.
- Los trabajos caducan, se pueden cancelar y no aceptan resultados de una
  reserva antigua. El trabajador elimina periódicamente los resultados vencidos.

Los cálculos de cobertura y diferencias usan `POST /api/tasks` o
`POST /api/analysis/jobs`. Una parada sin precálculo devuelve un trabajo `202`;
la interfaz consulta su resultado sin construir el grafo dentro de esa petición.
Las rutas GET antiguas de cálculos masivos devuelven `410` en una release inmutable.

Para la futura web, usa `compose.yaml` con datos montados en sólo lectura,
credenciales distintas para lector y administrador y dominio en `OBS_ALLOWED_HOSTS`.
El proxy tiene una dirección privada explícita para atribuir correctamente los
límites de peticiones a cada cliente. El trabajador tiene su propia comprobación
de salud y los registros de contenedores tienen rotación.

Antes de publicarla siguen siendo necesarios el ensayo real de Docker/Caddy,
HTTPS, copia externa y monitorización del servidor. Las funciones de carga no
se ofrecen en el visor publicado: la administración de datos permanece en staging.
