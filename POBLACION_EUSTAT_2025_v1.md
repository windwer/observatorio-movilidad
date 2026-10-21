# Población incluida en v1

La entrega contiene los valores oficiales de Eustat con referencia 01/01/2025
y los conserva en el mismo SQLite que utiliza el visor.

| Ámbito | Secciones | Habitantes |
|---|---:|---:|
| Bidasoaldea | 54 | 77.625 |
| Oarsoaldea | 55 | 73.207 |
| Total seis municipios | 109 | 150.832 |

La validación comprueba que las secciones suman los subtotales publicados por
distrito. Estos datos son la **base poblacional territorial**. La capa de
secciones censales y la red peatonal OSM incluidas permiten estimar la población
objetivo de cada isócrona por intersección proporcional de área, tanto para una
parada como para el recorrido completo, deduplicando las áreas solapadas. Al no
haber edificios residenciales en el paquete, el resultado es una estimación
territorial (no una asignación dasimétrica ni demanda observada).
