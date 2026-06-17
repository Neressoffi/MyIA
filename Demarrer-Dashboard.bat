@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title JARVIS - Dashboard administrateur
cd /d "%~dp0"

set JARVIS_ADMIN_PORT=8767

echo ============================================
echo       DASHBOARD ADMIN JARVIS
echo ============================================
echo.
echo  JARVIS chat    : http://127.0.0.1:8765
echo  Dashboard admin: http://127.0.0.1:%JARVIS_ADMIN_PORT%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Erreur : lancez d'abord Demarrer-JARVIS.bat pour installer l'environnement.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo [1/4] Arret de l'ancienne instance dashboard ^(port %JARVIS_ADMIN_PORT%^)...
set JARVIS_SERVER_PORT=%JARVIS_ADMIN_PORT%
.venv\Scripts\python.exe backend\stop_server.py
set JARVIS_SERVER_PORT=8765

echo [2/4] Demarrage du serveur dashboard...
start "JARVIS-Dashboard" /MIN cmd /c "cd /d %~dp0 && set JARVIS_ADMIN_PORT=%JARVIS_ADMIN_PORT% && .venv\Scripts\python.exe -m uvicorn backend.admin_server:app --host 127.0.0.1 --port %JARVIS_ADMIN_PORT%"

echo [3/4] Verification du serveur...
set JARVIS_ADMIN_PORT=%JARVIS_ADMIN_PORT%
.venv\Scripts\python.exe backend\wait_admin_ready.py
if errorlevel 1 (
    echo.
    echo ECHEC : le dashboard ne repond pas.
    pause
    exit /b 1
)

echo [4/4] Ouverture du navigateur...
start "" msedge "http://127.0.0.1:%JARVIS_ADMIN_PORT%/?v=%RANDOM%" || start "" "http://127.0.0.1:%JARVIS_ADMIN_PORT%/?v=%RANDOM%"

echo.
echo ============================================
echo  Dashboard pret : http://127.0.0.1:%JARVIS_ADMIN_PORT%
echo  Mot de passe : admin_password.txt
echo  NE FERMEZ PAS la fenetre "JARVIS-Dashboard".
echo  Lancez aussi Demarrer-JARVIS.bat pour le chat.
echo ============================================
echo.
pause
