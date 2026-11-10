#!/usr/bin/env bash
# Démarrage de « Suivi des dossiers » sous Linux / macOS.
# Double-clic possible si le fichier est marqué exécutable, sinon :
#   ./demarrer.sh          ou          bash demarrer.sh
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.10+ est introuvable."
  echo "Installez-le (Debian/Ubuntu : sudo apt install python3 python3-venv) puis relancez."
  read -r -p "Appuyez sur Entrée pour fermer…" _
  exit 1
fi

exec "$PY" lancer.py "$@"
