# Product Review — Red peatonal e isócronas (v0.6.4)

## Estado

La demo incorpora una red peatonal real de OpenStreetMap (11.400 vías, 65.382 segmentos derivados) en ventanas urbanas alrededor de las paradas DEMO. Las líneas, horarios y paradas de transporte siguen siendo sintéticos y no se conecta Transitland.

Las isócronas ya no se calculan como círculos, cruces ni buffers radiales: el motor ejecuta Dijkstra sobre la red OSM, a 4,5 km/h, y crea una envolvente cóncava de los nodos y fronteras alcanzados. La población se comprueba parada a parada por distancia de red y se deduplica al agregar un recorrido completo.

## Qué revisar

1. Ejecuta `run_product_review_windows.bat` y abre la URL nueva que indique el iniciador.
2. Confirma la cabecera **DEMO v0.6.3 · Red peatonal OSM real**.
3. Selecciona Irunbus → L1. El KPI **Población cubierta · recorrido** debe dejar de mostrar 0 y mostrar la cobertura única a 10 minutos de todas sus paradas.
4. Haz clic en una parada: el mapa muestra 5 min naranja y 10 min azul; el texto identifica la parada y el KPI mantiene la cobertura agregada del recorrido.
5. Cambia a otra línea y comprueba que el KPI se recalcula para ese recorrido. Sin línea seleccionada, calcula toda la red del operador.
6. Comprueba que la cobertura no suma dos veces la misma unidad residencial cuando dos paradas alcanzan el mismo edificio.

## Límites de Product Review

- La población es una estimación exploratoria: población Eustat asignada a edificios residenciales OSM por superficie × plantas. No es demanda, ni servicio observado, ni una cifra certificada.
- La red OSM se ha descargado en ventanas acotadas alrededor de las paradas DEMO. Fuera de esas ventanas una parada puede quedar sin conexión.
- La envolvente cartográfica facilita la lectura; la población usa distancia de red a la entrada residencial, no solo inclusión visual en el polígono.
- Las teselas GeoEuskadi/Esri requieren Internet. Transitland y las descargas de transporte permanecen bloqueados en Product Review.

## Criterios de aceptación

- CA-ISO-01: 5 y 10 minutos son geometrías orgánicas, válidas y anidadas para una misma parada.
- CA-ISO-02: la geometría procede de Dijkstra sobre vías OSM identificadas, no de un radio.
- CA-ISO-03: la población de parada y la población de recorrido son dos medidas distintas y explícitas.
- CA-COV-01: la población de recorrido se deduplica por unidad residencial entre todas las paradas.
- CA-COV-02: la interfaz recalcula la cobertura al cambiar operador o línea.
- CA-DEMO-01: la pantalla conserva el aviso de datos DEMO y de estimación no certificada.
- CA-DEMO-02: Product Review no llama Transitland ni expone claves API.
