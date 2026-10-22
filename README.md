# Observatorio de Movilidad · Gipuzkoa

Visor reproducible para analizar red, oferta y accesibilidad peatonal de
Irunbus, Ekialdebus, Euskotren (líneas ferroviarias E1/E2) y Errenteria bus
urbano, con histórico GTFS local y referencia poblacional Eustat 2025. La entrega corresponde al paquete histórico `v1` y a la aplicación
`v1.0`; mantiene la fase de
Product Review: los horarios GTFS describen oferta programada, no prueban por sí
solos el servicio prestado.

## Qué contiene este repositorio

- Código del visor, motor de red, isócronas y métricas de línea.
- Catálogo seleccionable de las cuatro redes del ámbito; el mapa combinado
  histórico conserva el par de autobuses original y las nuevas redes se
  consultan de forma independiente.
- Red peatonal OSM provincial y trazabilidad de las importaciones históricas.
- Tabla y metadatos Eustat 2025 para los 88 municipios de Gipuzkoa: 544
  secciones y 724.797 habitantes de referencia.
- Pruebas y un flujo de QA para sintaxis y validación de la referencia
  poblacional.

El histórico completo conserva 160 cortes GTFS (80 Irunbus y 80 Ekialdebus), la
base SQLite y los archivos originales descargados. La base de ejecución incluye
además las instantáneas actuales de Euskotren E1/E2 y Errenteria bus urbano
capturadas el 21/10/2026. Esos archivos no se incluyen
en el commit de GitHub: la base ronda 2 GB y un ZIP completo supera el límite
normal de archivos de GitHub. Se mantienen en el paquete histórico v1 y se
preparan localmente con el script incluido.

## Preparar los datos históricos

Desde PowerShell, en la raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_runtime_data.ps1 `
  -PackagePath "C:\ruta\al\paquete\Observatorio_Movilidad_historico_completo_v1_20261020.zip"
```

`PackagePath` también puede ser la carpeta ya descomprimida. El script copia la
base, los originales GTFS, los informes de importación y la red peatonal. Luego
ejecuta `EJECUTAR_OBSERVATORIO_HISTORICO_v1.bat`; se crea el entorno virtual,
se instalan las dependencias y se abre el visor en el puerto 8870.

## Población y cobertura

La población Eustat incluida es una referencia territorial provincial validada.
El visor cruza las 544 secciones censales 2025 con la red peatonal OSM provincial
y la isócrona de red para mostrar una estimación de población objetivo,
deduplicada entre paradas. La superficie dibujada sólo sigue tramos peatonales
alcanzables; no se usa una envolvente radial que atraviese campos o manzanas.

## Alcance y límites

- No se conectan APIs Transitland en esta entrega.
- La disponibilidad de un feed GTFS no equivale a servicio observado.
- Los datos históricos son snapshots fechados y se preservan sin deduplicar
  contenidos idénticos capturados en fechas distintas.

## Licencia y fuentes

Consulta las notas de integración y los archivos de referencia en
`data/references/` antes de redistribuir datos de terceros. Las fuentes y
condiciones de uso deben mantenerse junto con cada snapshot.
