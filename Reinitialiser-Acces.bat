@echo off
chcp 65001 >nul
title Reinitialiser l'acces JARVIS
cd /d "%~dp0"
set JARVIS_SERVER_PORT=8765

echo ============================================
echo   REINITIALISER L'ACCES JARVIS
echo ============================================
echo.
echo Cela supprime le mot de passe actuel.
echo Vous pourrez en creer un nouveau au prochain lancement.
echo.

echo [1/3] Arret du serveur...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe backend\stop_server.py
)

echo [2/3] Suppression de l'ancien mot de passe...
if exist ".jarvis_auth" del /f /q ".jarvis_auth"

echo [3/3] Relance de JARVIS...
call "%~dp0Demarrer-JARVIS.bat"
