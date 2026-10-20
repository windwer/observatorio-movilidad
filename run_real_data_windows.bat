@echo off
setlocal
cd /d "%~dp0"
set "OBS_DEMO=0"
set "OBS_DB=%CD%\data\real\observatorio_real.sqlite3"
set "OBS_PORT=8870"
call run_windows.bat
