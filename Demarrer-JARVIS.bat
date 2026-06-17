@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title JARVIS - Assistant IA local
cd /d "%~dp0"

set JARVIS_SERVER_PORT=8765

echo ============================================
echo            DEMARRAGE DE JARVIS
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Premiere installation...
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
    python -m pip install -r requirements.txt -q
)

echo [2/5] Arret de l'ancienne instance ^(port %JARVIS_SERVER_PORT%^)...
.venv\Scripts\python.exe backend\stop_server.py
if errorlevel 1 (
    echo Attention : port occupe, tentative de demarrage quand meme...
)

echo [3/5] Demarrage du serveur securise...
start "JARVIS-Serveur" /MIN cmd /c "cd /d %~dp0 && set JARVIS_SERVER_PORT=%JARVIS_SERVER_PORT% && .venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port %JARVIS_SERVER_PORT%"

echo [4/5] Verification du serveur...
.venv\Scripts\python.exe backend\wait_ready.py
if errorlevel 1 (
    echo.
    echo ECHEC : le serveur ne repond pas.
    pause
    exit /b 1
)

echo [5/5] Ouverture du navigateur...
start "" msedge "http://127.0.0.1:%JARVIS_SERVER_PORT%/?v=%RANDOM%" || start "" "http://127.0.0.1:%JARVIS_SERVER_PORT%/?v=%RANDOM%"

echo.
echo ============================================
echo  JARVIS est pret : http://127.0.0.1:%JARVIS_SERVER_PORT%
echo  Creez votre mot de passe ^(min. 6 caracteres^).
echo  NE FERMEZ PAS la fenetre "JARVIS-Serveur".
echo ============================================
echo.
pause
