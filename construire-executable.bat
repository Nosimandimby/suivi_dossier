@echo off
rem Construit l'executable autonome Windows : dist\suivi-dossiers.exe
rem A executer sur une machine Windows disposant de Python 3.10+.
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 goto erreur

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

%PY% -m PyInstaller --noconfirm --clean --onefile ^
  --name suivi-dossiers ^
  --add-data "static;static" ^
  --collect-submodules uvicorn ^
  --collect-submodules fastapi ^
  --hidden-import main ^
  --hidden-import database ^
  --hidden-import seed ^
  --hidden-import chemins ^
  lancer.py
if errorlevel 1 goto erreur

echo.
echo Executable pret : dist\suivi-dossiers.exe
pause
exit /b 0

:erreur
echo.
echo La construction a echoue. Verifiez que Python 3.10+ et pip sont installes.
pause
exit /b 1
