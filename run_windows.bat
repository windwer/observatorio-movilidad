@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 where py >NUL 2>NUL
 if %errorlevel% EQU 0 (py -3 -m venv .venv) else (python -m venv .venv)
 if errorlevel 1 (echo ERROR: Se requiere Python 3.11 o posterior. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo ERROR: Fallo en dependencias. & pause & exit /b 1)
echo *** OBSERVATORIO v0.6.5 - ABRE AUTOMATICAMENTE LA VERSION NUEVA ***
echo Esta instancia usa el puerto configurado y abre la version del paquete actual.
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 echo Revisa el mensaje anterior para identificar el error.
pause
