# QA · Euskotren y Errenteria bus urbano · 21/10/2026

## Alcance

Se incorporan al paquete real las publicaciones GTFS estáticas oficiales de
Moveuskadi para ampliar el corredor Oarsoaldea–Bidasoaldea. La DEMO y el
histórico de Irunbus/Ekialdebus permanecen separados.

| Red | Servicio conservado | Vigencia GTFS | Rutas | Paradas | Viajes base | SHA-256 |
|---|---|---|---:|---:|---:|---|
| Euskotren (tren) | E1 Bilbao–Donostia y E2 Lasarte–Hendaia | 21/10/2026–30/11/2026 | 2 | 103 | 3.569 | `79f1940b9eccc1bf001628a10e0e1c702a9fb328fac97648eb7129614ef16150` |
| Errenteria bus urbano | U1, U2, U5, U6, U7, U11, U22, U33 y U44 | 19/10/2026–31/12/2026 | 9 | 82 | 293 | `3dfe97d2de370fdd9beace423d4011724a9bacd893218a662596624c1bfc7168` |

## Comprobaciones

- La ingesta de Euskotren filtra el feed multimodal para conservar solo E1/E2;
  no se presentan tranvías ni funicular como trenes del ámbito.
- Las tablas dependientes (`trips`, `stop_times`, `stops`, `shapes` y
  calendarios) se reducen junto con las rutas, sin referencias huérfanas.
- La consulta de calendario para 21/10/2026 devuelve servicio de planificación
  para E1/E2 y el catálogo de Errenteria devuelve sus nueve líneas.
- El selector de operador se reconstruye desde `/api/data/requirements`, por
  lo que no depende de que el HTML inicial conserve el catálogo más reciente.
- El mapa combinado existente sigue limitado a Ekialdebus + Irunbus; las dos
  redes nuevas se seleccionan de forma independiente para no alterar la
  comparación histórica de autobuses.
- La entrega contiene 109 polígonos censales Eustat y 65.382 tramos OSM. La
  interpolación proporcional de sección calcula población objetivo en cada
  parada y en el recorrido completo incluso sin edificios residenciales;
  la asignación a edificios sigue siendo una mejora opcional.

## Pruebas automatizadas

```text
python -m unittest test_network_additions test_engine test_territory
Ran 20 tests ... OK
```

Fuentes: [índice oficial Moveuskadi](https://www.euskadi.eus/contenidos/ds_movilidad/md_ideeu_moveuskadi/es_def/index.shtml),
[GTFS Euskotren](https://opendata.euskadi.eus/transport/moveuskadi/euskotren/gtfs_euskotren.zip) y
[GTFS Errenteria urbano](https://opendata.euskadi.eus/transport/moveuskadi/errenteria/gtfs_errenteriako_urbanoa.zip).
