@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title JARVIS - Demarrage complet
cd /d "%~dp0"

echo ============================================
echo     DEMARRAGE JARVIS + DASHBOARD
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Installation initiale via Demarrer-JARVIS.bat...
    call "%~dp0Demarrer-JARVIS.bat"
    exit /b %ERRORLEVEL%
)

call ".venv\Scripts\activate.bat"

set JARVIS_SERVER_PORT=8765
set JARVIS_ADMIN_PORT=8767

echo [1/5] Arret anciennes instances...
.venv\Scripts\python.exe backend\stop_server.py
set JARVIS_SERVER_PORT=8767
.venv\Scripts\python.exe backend\stop_server.py
set JARVIS_SERVER_PORT=8765

echo [2/5] Demarrage JARVIS chat ^(port 8765^)...
start "JARVIS-Serveur" /MIN cmd /c "cd /d %~dp0 && set JARVIS_SERVER_PORT=8765 && .venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765"

echo [3/5] Demarrage Dashboard admin ^(port 8767^)...
start "JARVIS-Dashboard" /MIN cmd /c "cd /d %~dp0 && set JARVIS_ADMIN_PORT=8767 && .venv\Scripts\python.exe -m uvicorn backend.admin_server:app --host 127.0.0.1 --port 8767"

echo [4/5] Verification...
.venv\Scripts\python.exe backend\wait_ready.py
if errorlevel 1 goto :echec
set JARVIS_ADMIN_PORT=8767
.venv\Scripts\python.exe backend\wait_admin_ready.py
if errorlevel 1 goto :echec

echo [5/5] Ouverture navigateur...
start "" msedge "http://127.0.0.1:8765/?v=%RANDOM%" || start "" "http://127.0.0.1:8765/?v=%RANDOM%"

echo.
echo ============================================
echo  JARVIS chat     : http://127.0.0.1:8765
echo  Dashboard admin : http://127.0.0.1:8767
echo  NE FERMEZ PAS les fenetres JARVIS-Serveur et JARVIS-Dashboard.
echo ============================================
echo.
pause
exit /b 0

:echec
echo ECHEC : un des serveurs ne repond pas.
pause
exit /b 1
