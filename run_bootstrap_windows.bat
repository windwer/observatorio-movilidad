@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 where py >NUL 2>NUL
 if %errorlevel% EQU 0 (py -3 -m venv .venv) else (python -m venv .venv)
 if errorlevel 1 (echo ERROR: Instala Python 3.11 o posterior. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo ERROR: Fallo al instalar dependencias. & pause & exit /b 1)
".venv\Scripts\python.exe" bootstrap_sources.py
pause
