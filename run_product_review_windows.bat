@echo off
echo Este paquete contiene las instantaneas GTFS reales entregadas por el usuario.
echo Ejecutando el mismo arranque real para evitar abrir una base DEMO vacia.
call "%~dp0run_real_data_windows.bat"
