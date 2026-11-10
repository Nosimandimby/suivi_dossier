"""Résolution des chemins de l'application, en mode source ou exécutable figé.

Deux notions distinctes :

- ``RESSOURCES_DIR`` : là où se trouvent les fichiers livrés en lecture seule
  (``static/``).  En mode source, c'est le dossier du projet ; dans un
  exécutable PyInstaller « one file », c'est le dossier temporaire d'extraction.
- ``HOME_DIR`` : là où vivent les données de l'utilisateur (``data/dossiers.db``).
  C'est toujours le dossier de l'application : dossier du projet en mode source,
  dossier de l'exécutable en mode figé.  Ainsi, copier le dossier (ou le seul
  exécutable) emporte les données et les écrit à côté de soi, jamais dans un
  répertoire temporaire effacé à la fermeture.
"""

from __future__ import annotations

import os
import sys


def _est_fige() -> bool:
    """Vrai lorsque l'application tourne depuis un exécutable PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def _dossier_executable() -> str:
    """Dossier de l'exécutable lancé (résolu, sans le nom du fichier)."""
    return os.path.dirname(os.path.abspath(sys.executable))


#: Dossier des ressources livrées (``static/``).
RESSOURCES_DIR = (
    os.path.abspath(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
    if _est_fige()
    else os.path.dirname(os.path.abspath(__file__))
)

#: Dossier de l'application : accueille ``data/`` et sert de base aux chemins.
HOME_DIR = _dossier_executable() if _est_fige() else os.path.dirname(os.path.abspath(__file__))


def chemin_donnees(*parties: str) -> str:
    """Chemin dans le dossier des données (``data/`` par défaut), créé au besoin."""
    dossier = os.environ.get("DOSSIER_DATA_DIR") or os.path.join(HOME_DIR, "data")
    dossier = os.path.abspath(os.path.expanduser(dossier))
    if parties:
        return os.path.join(dossier, *parties)
    return dossier


def preparer_donnees() -> str:
    """Crée le dossier des données s'il n'existe pas et renvoie son chemin."""
    dossier = chemin_donnees()
    os.makedirs(dossier, exist_ok=True)
    return dossier
