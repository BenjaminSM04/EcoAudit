@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0detener.ps1" %*
set "resultado=%errorlevel%"
if not "%resultado%"=="0" pause
exit /b %resultado%
