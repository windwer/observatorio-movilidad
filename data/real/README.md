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
ejecución. `EJECUTAR_OBSERVATORIO_HISTORICO_v1.bat` comprueba que la base exista
antes de iniciar el visor.

El repositorio incluye tablas de población Eustat 2025 y su validación. La
población de referencia (150.832 habitantes, seis municipios) no se presenta
como población cubierta por una línea: esa métrica solo debe calcularse cuando
estén disponibles y validadas las capas residenciales/geográficas necesarias.
