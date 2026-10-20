# Observatorio de Movilidad · Bidasoaldea y Oarsoaldea

Visor reproducible para analizar red, oferta y accesibilidad peatonal de
Irunbus y Ekialdebus, con histórico GTFS local y referencia poblacional Eustat
2025. La entrega corresponde a la versión de código `v1` y mantiene la fase de
Product Review: los horarios GTFS describen oferta programada, no prueban por sí
solos el servicio prestado.

## Qué contiene este repositorio

- Código del visor, motor de red, isócronas y métricas de línea.
- Red peatonal real ligera y trazabilidad de las importaciones históricas.
- Tablas y metadatos Eustat 2025: 109 secciones y 150.832 habitantes en los
  seis municipios del ámbito.
- Pruebas y un flujo de QA para sintaxis y validación de la referencia
  poblacional.

El histórico completo conserva 160 cortes GTFS (80 Irunbus y 80 Ekialdebus), la
base SQLite y los archivos originales descargados. Esos archivos no se incluyen
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

La población Eustat incluida es una referencia territorial validada. No debe
confundirse con “población cubierta por una línea”: esa cifra requiere una unión
espacial residencial verificada con la isócrona. El visor mantiene esa
distinción y no inventa cobertura cuando faltan esas capas.

## Alcance y límites

- No se conectan APIs Transitland en esta entrega.
- La disponibilidad de un feed GTFS no equivale a servicio observado.
- Los datos históricos son snapshots fechados y se preservan sin deduplicar
  contenidos idénticos capturados en fechas distintas.

## Licencia y fuentes

Consulta las notas de integración y los archivos de referencia en
`data/references/` antes de redistribuir datos de terceros. Las fuentes y
condiciones de uso deben mantenerse junto con cada snapshot.
