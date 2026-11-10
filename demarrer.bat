@echo off
rem Demarrage de "Suivi des dossiers" sous Windows : double-cliquez sur ce fichier.
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 lancer.py %*
  goto fin
)

where python >nul 2>&1
if %errorlevel%==0 (
  python lancer.py %*
  goto fin
)

echo.
echo Python 3.10 ou plus recent est introuvable.
echo Installez-le depuis https://www.python.org/downloads/windows/
echo (cochez "Add python.exe to PATH" pendant l'installation) puis relancez ce fichier.
echo.

:fin
if errorlevel 1 pause
pause
