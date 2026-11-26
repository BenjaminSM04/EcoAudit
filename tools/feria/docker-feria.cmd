@echo off
rem Arranque para el dia de la feria: no recompila ni descarga nada (funciona sin internet).
rem Requiere haber ejecutado antes docker-demo.cmd con internet.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-demo.ps1" -SinCompilar %*
set "resultado=%errorlevel%"
if not "%resultado%"=="0" pause
exit /b %resultado%
