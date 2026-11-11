# Suivi des dossiers

Application locale et entièrement hors ligne de gestion de dossiers
administratifs :

- **Backend :** Python + FastAPI
- **Base de données :** SQLite (un seul fichier, facile à sauvegarder)
- **Interface :** HTML/CSS/JS simple (aucun framework, aucune compilation, aucun CDN)

Tout fonctionne sur votre machine, sans dépendance cloud.

## Prérequis

- Python 3.10 ou plus récent (développé et testé sur 3.12), avec le module
  `venv` — sous Debian/Ubuntu : `sudo apt install python3 python3-venv`.
- **Aucune connexion Internet** n'est nécessaire : les paquets Python
  (`fastapi`, `uvicorn` et leurs dépendances) sont livrés dans `dependances/`.

## Lancement (une seule commande)

```bash
python3 lancer.py            # Windows : py -3 lancer.py
```

Ou, sans taper de commande :

- **Linux/macOS :** double-clic sur `demarrer.sh` (ou `./demarrer.sh`) ;
- **Windows :** double-clic sur `demarrer.bat`.

Le lanceur :

1. vérifie la présence de Python 3.10+ ;
2. installe les dépendances **hors ligne** dans un environnement local
   `runtime/` créé dans le dossier de l'application (rien n'est modifié dans le
   Python du système) ;
3. démarre le serveur sur le premier port libre à partir de 8000 et **ouvre le
   navigateur** automatiquement.

Options utiles :

```bash
python3 lancer.py --port 8080       # port de départ
python3 lancer.py --host 0.0.0.0    # accessible depuis le réseau local
python3 lancer.py --no-browser      # ne pas ouvrir le navigateur
python3 lancer.py --reinstall       # réinstaller les dépendances locales
```

Ouvrez ensuite <http://127.0.0.1:8000> si le navigateur ne s'est pas ouvert.

## Installer sur une autre machine (copie du dossier)

1. Copiez **tout** le dossier de l'application sur la clé USB ou sur l'autre
   machine (les fichiers suivants sont indispensables) :

   ```
   lancer.py  demarrer.sh  demarrer.bat
   main.py  database.py  seed.py  chemins.py  static/
   dependances/            <- paquets Python hors ligne (Linux + Windows)
   data/                   <- vos dossiers (facultatif pour un démarrage vierge)
   ```
   `runtime/` et `__pycache__/` sont recréés automatiquement : inutile de les
   copier.

2. Sur la machine d'arrivée, lancez `demarrer.sh` (Linux/macOS) ou
   `demarrer.bat` (Windows), ou bien `python3 lancer.py`.

C'est tout : aucune installation, aucun droit administrateur, aucune connexion
Internet. La base reste le fichier `data/dossiers.db`, **à côté du programme**,
quel que soit le dossier depuis lequel la commande est lancée.

Les paquets fournis couvrent **Linux x86_64** et **Windows 64 bits** pour
Python 3.10, 3.11, 3.12, 3.13 et 3.14. Si la machine n'a pas de Python, utilisez
plutôt l'exécutable autonome ci-dessous.

## Exécutable autonome (sans Python installé)

### Linux

Un binaire unique est déjà construit dans `dist/suivi-dossiers` (16 Mo,
aucune dépendance externe). Copiez uniquement ce fichier où vous voulez, puis :

```bash
chmod +x suivi-dossiers     # une seule fois
./suivi-dossiers
```

Il crée son dossier `data/` à côté de lui-même et ouvre le navigateur.

### Windows

Un `.exe` ne peut être produit que depuis Windows. Sur la machine Windows
souhaitée (avec Python 3.10+ installé), double-cliquez sur
`construire-executable.bat` : le fichier `dist\suivi-dossiers.exe` est créé et
peut ensuite être copié seul sur n'importe quel PC Windows 64 bits, sans Python.

Pour reconstruire l'exécutable Linux : `bash construire-executable.sh`
(nécessite `pyinstaller`, listé dans `requirements-dev.txt`).


## Installation « développeur » (facultatif)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python main.py                   # démarrage direct, sans le lanceur
```

Le premier lancement crée automatiquement `data/dossiers.db` (emplacement du
fichier SQLite), les points de contrôle par type et le compte administrateur par
défaut. Le script `python seed.py` fait la même chose et peut être relancé sans
risque (idempotent).

Variables d'environnement facultatives : `PORT` (défaut `8000`), `HOST` (défaut
`127.0.0.1`), `DOSSIER_DB_PATH` (défaut `data/dossiers.db`).

## Connexion administrateur par défaut

| Identifiant | Mot de passe |
|-------------|--------------|
| `admin` | `admin` |

La connexion se fait **uniquement par nom d'utilisateur** (les comptes n'ont pas
d'email). Un compte désactivé ne peut plus se connecter, et ses sessions
ouvertes sont coupées.

## Numérotation (règle principale)

Chaque type de dossier possède sa propre plage de numéros et son propre
compteur. Les compteurs vivent dans la table SQLite `counters` : la numérotation
est **persistante et jamais remise à zéro par un redémarrage**, et chaque type
progresse indépendamment.

| Type | Plage | Exemples |
|------|-------|----------|
| Affichage | 001 → 199 | `001`, `002`, … `199` |
| Personnel | 200 → 399 | `200`, `201`, … `399` |
| Autres | 400 → 599 | `400`, `401`, … `599` |
| Marché | 600 → 799 | `600`, `601`, … `799` |
| Décision | 800 → 999 | `800`, `801`, … `999` |
| DEF/TEF | 1000 et suivants | `1000`, `1001`, … |

- Les numéros sont affichés sur trois chiffres minimum (`001`, `010`), puis sans
  limite (`1000`).
- **Le nombre de dossiers par type ne peut pas dépasser sa plage** : une fois le
  dernier numéro attribué, la création d'un nouveau dossier de ce type est
  refusée avec un message explicite (erreur 409).
- Le numéro est attribué automatiquement, dans la même transaction que
  l'insertion, donc deux créations simultanées ne peuvent jamais recevoir le
  même numéro.
- Le **type est définitif après création**, puisqu'il détermine la plage de
  numéros.

## Règles métier

- **Deux notions distinctes :** l'**état** (`Reçu`, `Retiré`) décrit la
  présence physique du dossier, le **statut** (`En cours`, `Visé`, `Rejeté`,
  `Retour`) décrit son avancement. Un nouveau dossier démarre à l'état `Reçu` et au
  statut `En cours`, tous deux modifiables dès la création.
- **Retirer un dossier :** depuis la fiche du dossier, le bouton « Retirer »
  passe l'état à `Retiré`, enregistre le **nom de la personne qui retire** et
  la **date de retrait** (date du jour), avec une **remarque facultative**.
  Le bouton devient « Annuler le retrait » et remet le dossier à `Reçu` en
  effaçant la date et le nom.
- **Statut « Retour » :** retirer un dossier encore au statut `En cours` le
  fait passer automatiquement à `Retour` (il revient sans avoir été visé). Un
  statut déjà tranché (`Visé`, `Rejeté`) est conservé.
- **Changer le statut :** depuis la fiche du dossier, le bouton « Changer le
  statut » permet de passer à `En cours`, `Visé`, `Rejeté` ou `Retour`, avec une
  **remarque facultative** (utile en cas de rejet).
- **Date du dossier :** renseignée automatiquement avec la date du jour, mais
  **modifiable manuellement** (format `AAAA-MM-JJ`).
- **Date de retrait :** renseignée automatiquement lors du passage à l'état
  `Retiré`, puis effacée si le dossier revient à `Reçu`.
- **Observation :** champ libre facultatif, présent à la création comme à la
  modification et affiché dans le détail.
- **Suppression :** le bouton « Supprimer » fait une **suppression logique** —
  la ligne reste en base avec son horodatage `deleted_at`, mais le dossier
  disparaît des listes, du tableau de bord et du détail.
- **Vérificateur :** toujours pris côté serveur depuis la session — le corps de
  la requête est ignoré et le champ est en lecture seule dans l'interface.
- **Remarques :** observation libre (sans verdict) ; l'auteur vient toujours de
  la session. Les remarques saisies lors d'un retrait ou d'un changement de
  statut apparaissent dans la liste des remarques du dossier.
- **Dossier parent :** facultatif ; l'auto-référence, les cycles et les dossiers
  supprimés sont refusés.

## Gestion des utilisateurs

L'onglet **Utilisateurs** permet de créer, modifier et supprimer des comptes :

- création avec identifiant, nom affiché, mot de passe, rôle et état actif ;
- l'identifiant est l'unique moyen de connexion et devient définitif ;
- un compte désactivé ne peut plus se connecter (sessions coupées) ;
- suppression impossible pour son propre compte, ou pour un compte lié à des
  dossiers ou des remarques.

## Données de départ

`seed.py` insère :

- le **catalogue des points de contrôle** (30 contrôles — cinq par type — avec
  l'indicateur obligatoire),
- le compte administrateur `admin` / `admin`.

Il est idempotent (`INSERT OR IGNORE`) et s'exécute aussi automatiquement au
démarrage de l'application.

## Sauvegarde

Arrêtez l'application (ou copiez simplement le fichier) et copiez l'unique
fichier de base :

```bash
cp data/dossiers.db data/dossiers-backup-$(date +%F).db
```

Restaurez en replaçant la sauvegarde à l'emplacement `data/dossiers.db`.

## Aperçu de l'API

Toutes les routes sauf `POST /api/login` exigent
`Authorization: Bearer <token>`.

| Méthode | Chemin | Rôle |
|---------|--------|------|
| POST | `/api/login` | connexion `{identity, password}` → `{token, user}` |
| POST | `/api/logout` | invalide le jeton de session |
| GET | `/api/me` | utilisateur courant |
| GET | `/api/meta` | types (plages + prochain numéro), états, statuts, rôles |
| GET | `/api/users` | utilisateurs + nombre de dossiers |
| POST | `/api/users` | créer un utilisateur |
| PUT | `/api/users/{id}` | modifier nom affiché, rôle, état actif, mot de passe |
| DELETE | `/api/users/{id}` | supprimer un compte sans données liées |
| GET | `/api/checkpoints?type=Affichage` | points de contrôle par type |
| GET | `/api/dossiers?type=&state=&status=&verifier_id=` | liste filtrable (hors supprimés) |
| POST | `/api/dossiers` | création (numéro auto, état `Reçu`, statut `En cours`, vérificateur) |
| GET | `/api/dossiers/{id}` | détail complet du dossier |
| PUT | `/api/dossiers/{id}` | modifier nom/état/statut/date/parent/observation |
| POST | `/api/dossiers/{id}/withdraw` | passer à `Retiré` : `{withdrawn_by, remark?}` |
| POST | `/api/dossiers/{id}/receive` | revenir à `Reçu` : `{remark?}` |
| POST | `/api/dossiers/{id}/status` | changer le statut : `{status, remark?}` |
| DELETE | `/api/dossiers/{id}` | suppression logique (`deleted_at`) |
| GET | `/api/dossiers/{id}/remarks` | remarques, plus récentes d'abord |
| POST | `/api/dossiers/{id}/remarks` | ajouter une remarque (auteur = session) |
| GET | `/api/dashboard` | compteurs par type/statut + activité récente |

La documentation interactive de l'API est servie sur
<http://127.0.0.1:8000/docs> (toujours hors ligne).

## Structure du projet

```
lancer.py                 lanceur unique : dépendances locales puis démarrage + navigateur
chemins.py                chemins de l'app et de data/ (mode source ou exécutable)
main.py                   application FastAPI, routes, authentification, point d'entrée
database.py               schéma SQLite, connexion, migration, règles de numérotation
seed.py                   peuplement : points de contrôle + compte admin
static/                   index.html, app.js, style.css (simples, sans compilation)
data/dossiers.db          fichier SQLite créé au premier lancement (à côté du programme)
dependances/{linux,windows}/py3xx/  paquets Python hors ligne par plateforme/version
runtime/                 environnement Python local créé au premier lancement (jetable)
dist/suivi-dossiers      exécutable Linux autonome
requirements.txt          fastapi + uvicorn
requirements-dev.txt      pyinstaller (uniquement pour construire l'exécutable)
construire-executable.sh  construction du binaire Linux/macOS
construire-executable.bat construction du binaire Windows
repository.yaml           déclaration du dépôt d'add-ons Home Assistant
suivi_dossiers/           add-on Home Assistant (config.yaml, Dockerfile, run.sh, DOCS.md)
suivi_dossiers/app/       copie du code livrée à l'add-on (générée par synchroniser-addon.sh)
synchroniser-addon.sh     recopie le code dans suivi_dossiers/app/
```
