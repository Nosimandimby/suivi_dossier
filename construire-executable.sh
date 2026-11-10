#!/usr/bin/env bash
# Construit l'exécutable autonome Linux/macOS : dist/suivi-dossiers
# Prérequis : Python 3.10+ et les dépendances de développement (requirements-dev.txt).
set -e
cd "$(dirname "$0")"

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

"$PY" -m pip install --quiet --upgrade pyinstaller

rm -rf build dist

"$PY" -m PyInstaller \
  --noconfirm --clean --onefile \
  --name suivi-dossiers \
  --add-data "static:static" \
  --collect-submodules uvicorn \
  --collect-submodules fastapi \
  --hidden-import main \
  --hidden-import database \
  --hidden-import seed \
  --hidden-import chemins \
  lancer.py

echo
echo "Exécutable prêt : dist/suivi-dossiers"
