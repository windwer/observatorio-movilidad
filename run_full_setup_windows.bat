@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 where py >NUL 2>NUL
 if %errorlevel% EQU 0 (py -3 -m venv .venv) else (python -m venv .venv)
 if errorlevel 1 (echo ERROR: se requiere Python 3.11+ & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements-geo.txt
if errorlevel 1 (echo Error al instalar dependencias & pause & exit /b 1)
echo Iniciando descarga e integracion de fuentes permitidas. No se inventaran datos.
".venv\Scripts\python.exe" full_setup.py
pause
