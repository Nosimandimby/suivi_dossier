#!/usr/bin/env bash
# Démarrage de l'add-on « Suivi des dossiers ».
# /data est le volume persistant géré par Home Assistant : il survit aux mises à
# jour et est inclus dans les sauvegardes Home Assistant.
set -euo pipefail

export DOSSIER_DATA_DIR="/data"
export HOST="0.0.0.0"
export PORT="8000"

mkdir -p "$DOSSIER_DATA_DIR"

# Import unique d'une base existante déposée dans le dossier partagé /share
# (par exemple une base venue d'une installation locale).
if [ ! -f "${DOSSIER_DATA_DIR}/dossiers.db" ] && [ -f /share/dossiers.db ]; then
    cp /share/dossiers.db "${DOSSIER_DATA_DIR}/dossiers.db"
    echo "[INFO] Base existante importée depuis /share/dossiers.db"
fi

echo "[INFO] Suivi des dossiers - démarrage"
echo "[INFO] Base de données : ${DOSSIER_DATA_DIR}/dossiers.db"

cd /app
exec python3 /app/main.py
