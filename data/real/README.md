# Datos de ejecución

Esta carpeta contiene los recursos ligeros que permiten revisar el visor y la
referencia poblacional. La base histórica SQLite y los ZIP originales GTFS no
se versionan en GitHub: la base supera los límites prácticos de un repositorio
normal y los cortes GTFS deben conservarse como archivos de distribución.

Para preparar una copia local con el histórico completo, descarga o conserva el
paquete `Observatorio_Movilidad_historico_completo_v1_*.zip` y ejecuta desde la
raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_runtime_data.ps1 `
  -PackagePath "C:\ruta\al\paquete\Observatorio_Movilidad_historico_v1"
```

También se admite pasar directamente el ZIP. El script copia la base, los
originales GTFS, los informes de importación y la red peatonal en sus rutas de
ejecución. La geometría oficial de las 544 secciones Eustat 2025 de Gipuzkoa se
conserva en `geography/census.geojson` y permite estimar población por
intersección de área;
los edificios residenciales son opcionales y mejoran la precisión. `EJECUTAR_OBSERVATORIO_HISTORICO_v1.bat`
comprueba que la base exista antes de iniciar el visor.

La base de ejecución incluye el histórico de Irunbus/Ekialdebus y las
instantáneas actuales de Euskotren E1/E2 y Errenteria bus urbano, capturadas
desde las publicaciones estáticas oficiales de Moveuskadi. El feed amplio de
Euskotren se filtra en la ingesta para conservar solo las líneas ferroviarias
del corredor; no se mezclan tranvías ni funicular.

El repositorio incluye la tabla provincial de población Eustat 2025 (724.797
habitantes en 88 municipios), su validación y la geometría oficial INE
Secciones_2025 de toda Gipuzkoa. La red peatonal provincial procede de
OpenStreetMap; la población se interpola proporcionalmente por sección dentro
de la isócrona y se deduplica entre paradas. El resultado es una estimación,
no demanda observada ni certificación de servicio.
