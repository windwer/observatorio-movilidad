@echo off
setlocal
cd /d "%~dp0"
set "OBS_DEMO=0"
set "OBS_DB=%CD%\data\real\observatorio_real.sqlite3"
set "OBS_PORT=8870"

if not exist "%OBS_DB%" (
  echo ERROR: no se encuentra la base historica en %OBS_DB%
  echo Ejecuta antes:
  echo powershell -ExecutionPolicy Bypass -File .\scripts\prepare_runtime_data.ps1 -PackagePath "C:\ruta\al\paquete_o_zip"
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  where py >NUL 2>NUL
  if %errorlevel% EQU 0 (py -3 -m venv .venv) else (python -m venv .venv)
  if errorlevel 1 (
    echo ERROR: se requiere Python 3.11 o posterior.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: no se pudieron instalar las dependencias.
  pause
  exit /b 1
)

echo *** OBSERVATORIO DE MOVILIDAD - HISTORICO COMPLETO v1 ***
echo Base: 160 cortes historicos + Euskotren E1/E2 + Errenteria urbano; poblacion Eustat 2025 Gipuzkoa (724797 habitantes)
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 echo Revisa el mensaje anterior para identificar el error.
pause
