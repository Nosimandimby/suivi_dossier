#!/usr/bin/env python3
"""Lanceur unique de « Suivi des dossiers ».

Usage (Linux, macOS, Windows) :

    python3 lancer.py            # ou : py lancer.py / double-clic sur demarrer.bat
    python3 lancer.py --port 8080 --no-browser

Ce que fait le script :

1. il vérifie que les dépendances (FastAPI, Uvicorn) sont disponibles ;
2. sinon, il crée un environnement local ``runtime/`` et les installe
   **hors ligne** depuis les roues (``.whl``) livrées dans ``dependances/`` ;
3. il démarre le serveur et ouvre le navigateur sur l'application.

Aucune connexion Internet n'est nécessaire et rien n'est installé dans le
Python du système : tout reste dans le dossier de l'application, qui peut donc
être copié tel quel sur une autre machine.
"""

from __future__ import annotations

import argparse
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

RACINE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(RACINE, "runtime")
DEPENDANCES = os.path.join(RACINE, "dependances")
MARQUEUR = os.path.join(RUNTIME, ".pret")
PAQUETS = ("fastapi", "uvicorn")

SERVEUR_PRET = threading.Event()


# ---------------------------------------------------------------------------
# Environnement Python local
# ---------------------------------------------------------------------------


def _python_runtime() -> str:
    """Chemin de l'interpréteur de l'environnement local ``runtime/``."""
    if platform.system() == "Windows":
        return os.path.join(RUNTIME, "Scripts", "python.exe")
    return os.path.join(RUNTIME, "bin", "python")


def _dependances_ok(python: str) -> bool:
    """Vrai si l'interpréteur donné peut importer FastAPI et Uvicorn."""
    if not os.path.exists(python):
        return False
    try:
        resultat = subprocess.run(
            [python, "-c", "import fastapi, uvicorn"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return resultat.returncode == 0


def _nom_plateforme() -> str:
    """Nom du sous-dossier de ``dependances/`` pour le système courant."""
    systeme = platform.system().lower()  # linux, windows, darwin
    return "windows" if systeme == "windows" else ("macos" if systeme == "darwin" else "linux")


def _dossier_roues(version: tuple[int, int] | None = None) -> str:
    """Roues correspondant au système et à la version majeure/mineure de Python."""
    if version is None:
        version = (sys.version_info.major, sys.version_info.minor)
    dossier = os.path.join(DEPENDANCES, _nom_plateforme(), f"py{version[0]}{version[1]}")
    return dossier if os.path.isdir(dossier) else os.path.join(DEPENDANCES, _nom_plateforme())


def _pip_disponible(python: str, environnement: dict[str, str] | None = None) -> bool:
    return subprocess.run(
        [python, "-c", "import pip"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environnement,
    ).returncode == 0


def _pip_embarque(python: str, environnement: dict[str, str]) -> bool:
    """Déploie le pip livré dans ``dependances/pip`` si l'interpréteur n'en a pas.

    Certaines distributions Debian livrent un module « venv » sans ``pip`` ni
    ``ensurepip`` ; cette solution de secours rend le dossier autonome quand même.
    """
    dossier_pip = os.path.join(DEPENDANCES, "pip")
    if not os.path.isdir(dossier_pip):
        return False
    roues = sorted(f for f in os.listdir(dossier_pip) if f.startswith("pip-") and f.endswith(".whl"))
    if not roues:
        return False

    import zipfile

    cible = os.path.join(RUNTIME, ".pip")
    os.makedirs(cible, exist_ok=True)
    with zipfile.ZipFile(os.path.join(dossier_pip, roues[-1])) as archive:
        archive.extractall(cible)

    ancien = environnement.get("PYTHONPATH")
    environnement["PYTHONPATH"] = cible + (os.pathsep + ancien if ancien else "")
    return _pip_disponible(python, environnement)


def _installer(python: str, roues: str) -> bool:
    """Installe les dépendances ; hors ligne d'abord, en ligne en secours."""
    environnement = dict(os.environ)
    if not _pip_disponible(python):
        subprocess.run([python, "-m", "ensurepip", "--upgrade"], env=environnement,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _pip_disponible(python) and not _pip_embarque(python, environnement):
        print("  pip est introuvable : installation impossible.", flush=True)
        return False

    base = [python, "-m", "pip", "install", "--no-input", "--disable-pip-version-check"]
    if os.path.isdir(roues) and any(f.endswith(".whl") for f in os.listdir(roues)):
        print(f"  Installation hors ligne depuis {roues} …", flush=True)
        hors_ligne = base + ["--no-index", "--find-links", roues, *PAQUETS]
        if subprocess.run(hors_ligne, env=environnement).returncode == 0:
            return True
        print("  Installation hors ligne impossible, tentative en ligne …", flush=True)
    return subprocess.run(base + list(PAQUETS), env=environnement).returncode == 0


def preparer_environnement(force: bool = False) -> str:
    """Garantit un interpréteur disposant des dépendances et le renvoie."""
    if getattr(sys, "frozen", False):
        # Exécutable autonome : les dépendances sont déjà embarquées.
        return sys.executable

    python = _python_runtime()

    if not force and os.path.exists(MARQUEUR) and _dependances_ok(python):
        return python

    # L'interpréteur courant a-t-il déjà tout ce qu'il faut ?
    if not force and _dependances_ok(sys.executable) and not os.path.isdir(RUNTIME):
        return sys.executable

    if force or not _dependances_ok(python):
        if not os.path.exists(python):
            print("  Création de l'environnement local (runtime/) …", flush=True)
            resultat = subprocess.run(
                [sys.executable, "-m", "venv", "--clear" if force else "--without-pip", RUNTIME]
            )
            if resultat.returncode != 0:
                resultat = subprocess.run([sys.executable, "-m", "venv", "--clear", RUNTIME])
            if resultat.returncode != 0:
                raise SystemExit(
                    "Impossible de créer l'environnement local.\n"
                    "Sous Debian/Ubuntu, installez le paquet python3-venv puis relancez."
                )

        if not _installer(python, _dossier_roues()):
            raise SystemExit(
                "L'installation des dépendances a échoué.\n"
                "Vérifiez que le dossier dependances/ a bien été copié, "
                "ou connectez-vous à Internet une première fois."
            )
        with open(MARQUEUR, "w", encoding="utf-8") as fichier:
            fichier.write("ok\n")

    if not _dependances_ok(python):
        raise SystemExit("L'environnement local est incomplet ; supprimez runtime/ et relancez.")
    return python


# ---------------------------------------------------------------------------
# Réseau
# ---------------------------------------------------------------------------


def port_disponible(port: int, hote: str) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((hote if hote not in ("0.0.0.0", "") else "0.0.0.0", port))
        except OSError:
            return False
    return True


def trouver_port(port_demande: int, hote: str) -> int:
    """Renvoie le port demandé, ou le suivant libre s'il est déjà occupé."""
    for port in range(port_demande, port_demande + 20):
        if port_disponible(port, hote):
            return port
    raise SystemExit(f"Aucun port libre entre {port_demande} et {port_demande + 19}.")


def ouvrir_navigateur(url: str, delai: float = 45.0) -> None:
    """Ouvre le navigateur dès que le serveur répond (au plus ``delai`` secondes)."""
    limite = time.time() + delai
    while time.time() < limite:
        try:
            with urllib.request.urlopen(url, timeout=2):
                break
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    try:
        webbrowser.open(url)
    except Exception:  # navigateur indisponible : l'adresse reste affichée
        pass


# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------


def analyser_arguments(argv: list[str]) -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(description="Lance l'application Suivi des dossiers.")
    analyseur.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8000),
                           help="port d'écoute (8000 par défaut)")
    analyseur.add_argument("--host", default=os.environ.get("HOST") or "0.0.0.0",
                           help="adresse d'écoute (127.0.0.1 par défaut, 0.0.0.0 pour le réseau local)")
    analyseur.add_argument("--no-browser", action="store_true",
                           help="ne pas ouvrir le navigateur automatiquement")
    analyseur.add_argument("--reinstall", action="store_true",
                           help="réinstaller les dépendances dans runtime/")
    return analyseur.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = analyser_arguments(list(sys.argv[1:] if argv is None else argv))

    print("=" * 60, flush=True)
    print("  Suivi des dossiers", flush=True)
    print("=" * 60, flush=True)
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 ou plus récent est requis (version actuelle : "
                         f"{platform.python_version()}).")

    print(f"  Python {platform.python_version()} détecté.", flush=True)
    print("  Préparation de l'application …", flush=True)

    python = preparer_environnement(force=options.reinstall)
    if not getattr(sys, "frozen", False):
        os.chdir(RACINE)

    if os.path.abspath(python) != os.path.abspath(sys.executable):
        # Relance le même script avec l'interpréteur de l'environnement local.
        commande = [python, os.path.abspath(__file__), *sys.argv[1:]]
        return subprocess.call(commande)

    port = trouver_port(options.port, options.host)
    if port != options.port:
        print(f"  Port {options.port} occupé, utilisation du port {port}.", flush=True)

    os.environ["PORT"] = str(port)
    os.environ["HOST"] = options.host
    url = f"http://{'127.0.0.1' if options.host in ('0.0.0.0', '') else options.host}:{port}"

    print(f"  Adresse : {url}", flush=True)
    print("  Connexion de démonstration : admin / admin", flush=True)
    print("  Arrêt : Ctrl+C (ou fermez cette fenêtre)", flush=True)
    print("=" * 60, flush=True)

    if not options.no_browser:
        threading.Thread(target=ouvrir_navigateur, args=(url,), daemon=True).start()

    import main as application

    return application.main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Application arrêtée.", flush=True)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as erreur:  # message lisible même en double-clic
        print(f"\n  Erreur : {erreur}", flush=True)
        if platform.system() == "Windows":
            input("\n  Appuyez sur Entrée pour fermer …")
        sys.exit(1)
