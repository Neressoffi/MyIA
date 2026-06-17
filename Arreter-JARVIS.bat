@echo off
chcp 65001 >nul
title Arreter JARVIS
cd /d "%~dp0"
set JARVIS_SERVER_PORT=8765

echo Arret de JARVIS sur le port %JARVIS_SERVER_PORT%...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe backend\stop_server.py
) else (
    python backend\stop_server.py
)
echo Termine.
pause
