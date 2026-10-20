@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta primero run_windows.bat para preparar Python y dependencias.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" preflight.py --strict
if errorlevel 1 echo El proyecto sigue SIN aptitud de publicacion. Consulta el detalle anterior.
pause
