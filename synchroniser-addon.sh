#!/usr/bin/env bash
# Recopie le code de l'application dans suivi_dossiers/app/.
#
# Home Assistant ne transmet au moteur de construction Docker que le dossier de
# l'add-on : les fichiers de l'application doivent donc y être présents. Lancez
# ce script après toute modification du code, avant de publier / installer.
set -euo pipefail
cd "$(dirname "$0")"

DEST="suivi_dossiers/app"

rm -rf "$DEST"
mkdir -p "$DEST"
cp main.py database.py seed.py chemins.py requirements.txt "$DEST"/
cp -r static "$DEST"/
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "Add-on synchronisé : $DEST"
