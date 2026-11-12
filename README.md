# Suivi des dossiers 📁

Application locale et entièrement hors ligne de gestion de dossiers administratifs :

- **Backend :** Python + FastAPI
- **Base de données :** SQLite (un seul fichier, facile à sauvegarder)
- **Interface :** HTML/CSS/JS simple (aucun framework, aucune compilation, aucun CDN)

Tout fonctionne sur votre machine, sans dépendance cloud.

---

## 🚀 Installation rapide (Nouvelle machine)

L'application est conçue pour fonctionner **hors ligne** et ne nécessite aucune installation de dépendances via Internet.

### Prérequis
- **Python 3.10 ou plus récent** (développé sur 3.12). 
  *Sous Debian/Ubuntu : `sudo apt install python3 python3-venv`*
- **Git** (pour récupérer le projet).

### Étape 1 : Récupérer le projet
```bash
git clone https://github.com/Nosimandimby/suivi_dossier.git
cd suivi_dossier
```

### Étape 2 : Lancer l'application
Une seule commande suffit (le script installe les dépendances locales hors ligne et démarre le serveur) :

```bash
python3 lancer.py
```

* **Sur Windows :** `py -3 lancer.py`
* **Sans taper de commande (Linux/macOS) :** `./demarrer.sh`
* **Sans taper de commande (Windows) :** double-clic sur `demarrer.bat`

Le lanceur va :
1. Vérifier la présence de Python 3.10+.
2. Installer les dépendances **hors ligne** dans un environnement local `runtime/` (rien n'est modifié dans le Python du système).
3. Démarrer le serveur sur le premier port libre à partir de 8000 et **ouvrir le navigateur** automatiquement.

> **Accès :** Ouvrez <http://127.0.0.1:8000> si le navigateur ne s'est pas ouvert.
> **Compte par défaut :** `admin` / `admin`

### Options utiles au lancement
```bash
python3 lancer.py --port 8080       # Changer le port de départ
python3 lancer.py --host 0.0.0.0    # Rendre accessible depuis le réseau local
python3 lancer.py --no-browser      # Ne pas ouvrir le navigateur
python3 lancer.py --reinstall       # Réinstaller les dépendances locales
```

---

## 💾 Exécutable autonome (Sans Python installé)

Si la machine cible n'a pas Python, vous pouvez utiliser l'exécutable autonome.

### Linux
Un binaire unique est déjà construit dans `dist/suivi-dossiers`. Copiez uniquement ce fichier où vous voulez, puis :
```bash
chmod +x suivi-dossiers     # une seule fois
./suivi-dossiers
```

### Windows
Un `.exe` ne peut être produit que depuis Windows. Sur la machine Windows (avec Python 3.10+ installé), double-cliquez sur `construire-executable.bat`. Le fichier `dist\suivi-dossiers.exe` est créé et peut ensuite être copié seul sur n'importe quel PC Windows 64 bits, sans Python.

*(Pour reconstruire l'exécutable Linux : `bash construire-executable.sh`)*

---

## 🔄 Mise à jour de l'application (Workflow Git)

Lorsque vous modifiez le code sur votre machine de développement et que vous poussez sur GitHub :

1. **Sur la machine de production :**
   ```bash
   git pull
   ```
2. **Relancer l'application** (les dépendances locales sont conservées) :
   ```bash
   python3 lancer.py
   ```
   *(Si de nouvelles dépendances ont été ajoutées, lancez `python3 lancer.py --reinstall`)*

---

## ⚙️ Lancement automatique en permanence (systemd)

Par défaut, l'application s'arrête lorsque vous fermez le terminal. Si vous souhaitez qu'elle tourne en permanence en arrière-plan (par exemple sur un Raspberry Pi ou un serveur dédié), vous pouvez la configurer comme un service `systemd`.

> ⚠️ **Note :** Dans ce mode, l'application ne tentera plus d'ouvrir le navigateur automatiquement. Vous devrez y accéder via l'adresse IP de la machine.

### 1. Créer le fichier de service

```bash
sudo nano /etc/systemd/system/suivi-dossiers.service
```

### 2. Coller le contenu suivant

*(Adaptez `User` et `WorkingDirectory` à votre configuration réelle)*

```ini
[Unit]
Description=Suivi des dossiers (FastAPI)
After=network.target

[Service]
Type=simple
User=votre_utilisateur
WorkingDirectory=/home/votre_utilisateur/suivi_dossier
Environment="HOST=0.0.0.0"
Environment="PORT=8000"
# Démarrage direct sans le lanceur (les dépendances doivent être installées)
ExecStart=/usr/bin/python3 main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3. Activer et démarrer le service

```bash
sudo systemctl daemon-reload
sudo systemctl enable suivi-dossiers
sudo systemctl start suivi-dossiers
sudo systemctl status suivi-dossiers
```

### 4. Commandes utiles

```bash
sudo systemctl stop suivi-dossiers      # Arrêter le service
sudo systemctl restart suivi-dossiers   # Redémarrer après une mise à jour
sudo journalctl -u suivi-dossiers -f    # Voir les logs en temps réel
```

---

## 🛠 Installation « développeur » (Mode source)

Pour modifier le code et bénéficier du rechargement à chaud :

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python main.py                   # démarrage direct, sans le lanceur
```

Le premier lancement crée automatiquement `data/dossiers.db` (base SQLite), les points de contrôle par type et le compte administrateur par défaut. Le script `python seed.py` fait la même chose (idempotent).

**Variables d'environnement facultatives :** `PORT` (défaut `8000`), `HOST` (défaut `127.0.0.1`), `DOSSIER_DB_PATH` (défaut `data/dossiers.db`).

---

## 📦 Copie manuelle sur une autre machine (sans Git)

Si vous préférez copier le dossier via une clé USB, voici les fichiers indispensables :

```
lancer.py  demarrer.sh  demarrer.bat
main.py  database.py  seed.py  chemins.py  static/
dependances/            <- paquets Python hors ligne (Linux + Windows)
data/                   <- vos dossiers (facultatif pour un démarrage vierge)
```
*Note : `runtime/` et `__pycache__/` sont recréés automatiquement, inutile de les copier.*

La base reste le fichier `data/dossiers.db`, **à côté du programme**, quel que soit le dossier depuis lequel la commande est lancée.

---

## 🔐 Connexion administrateur par défaut

| Identifiant | Mot de passe |
|-------------|--------------|
| `admin` | `admin` |

La connexion se fait **uniquement par nom d'utilisateur** (les comptes n'ont pas d'email). Un compte désactivé ne peut plus se connecter, et ses sessions ouvertes sont coupées.

---

## 🔢 Numérotation (règle principale)

Chaque type de dossier possède sa propre plage de numéros et son propre compteur persistant (table SQLite `counters`).

| Type | Plage | Exemples |
|------|-------|----------|
| Affichage | 001 → 199 | `001`, `002`, … `199` |
| Personnel | 200 → 399 | `200`, `201`, … `399` |
| Autres | 400 → 599 | `400`, `401`, … `599` |
| Marché | 600 → 799 | `600`, `601`, … `799` |
| Décision | 800 → 999 | `800`, `801`, … `999` |
| DEF/TEF | 1000 et suivants | `1000`, `1001`, … |

- Les numéros sont affichés sur trois chiffres minimum (`001`), puis sans limite (`1000`).
- **Le nombre de dossiers par type ne peut pas dépasser sa plage** (erreur 409 si plein).
- Le numéro est attribué automatiquement dans la même transaction que l'insertion (pas de doublon).
- Le **type est définitif après création**, puisqu'il détermine la plage de numéros.

---

## ⚖️ Règles métier

- **État vs Statut :** L'**état** (`Reçu`, `Retiré`) décrit la présence physique. Le **statut** (`En cours`, `Visé`, `Rejeté`, `Retour`) décrit l'avancement. Un nouveau dossier démarre à l'état `Reçu` et au statut `En cours`.
- **Retirer un dossier :** Le bouton « Retirer » passe l'état à `Retiré`, enregistre le nom de la personne et la date du jour (remarque facultative). Le bouton devient « Annuler le retrait » pour revenir à `Reçu`.
- **Statut « Retour » :** Retirer un dossier au statut `En cours` le fait passer automatiquement à `Retour`. Un statut déjà tranché (`Visé`, `Rejeté`) est conservé.
- **Changer le statut :** Bouton « Changer le statut » pour passer à `En cours`, `Visé`, `Rejeté` ou `Retour` (remarque facultative).
- **Dates :** La date du dossier est renseignée automatiquement mais modifiable (format `AAAA-MM-JJ`). La date de retrait est automatique et effacée si le dossier revient à `Reçu`.
- **Observation :** Champ libre facultatif à la création et modification.
- **Suppression :** Le bouton « Supprimer » fait une **suppression logique** (la ligne reste en base avec `deleted_at`, mais disparaît des listes).
- **Vérificateur :** Toujours pris côté serveur depuis la session (lecture seule dans l'interface).
- **Remarques :** L'auteur vient toujours de la session. Elles apparaissent dans la liste des remarques du dossier.
- **Dossier parent :** Facultatif ; l'auto-référence, les cycles et les dossiers supprimés sont refusés.

---

## 👥 Gestion des utilisateurs

L'onglet **Utilisateurs** permet de créer, modifier et supprimer des comptes :
- Création avec identifiant, nom affiché, mot de passe, rôle et état actif.
- L'identifiant est l'unique moyen de connexion et devient définitif.
- Un compte désactivé ne peut plus se connecter (sessions coupées).
- Suppression impossible pour son propre compte, ou pour un compte lié à des dossiers/remarques.

---

## 🌱 Données de départ

`seed.py` insère le **catalogue des points de contrôle** (30 contrôles) et le compte administrateur `admin` / `admin`. Il est idempotent et s'exécute automatiquement au démarrage.

---

## 💾 Sauvegarde

Arrêtez l'application et copiez l'unique fichier de base :
```bash
cp data/dossiers.db data/dossiers-backup-$(date +%F).db
```
Restaurez en replaçant la sauvegarde à l'emplacement `data/dossiers.db`.

---

## 🔌 Aperçu de l'API

Toutes les routes sauf `POST /api/login` exigent `Authorization: Bearer <token>`.

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

La documentation interactive de l'API est servie sur <http://127.0.0.1:8000/docs> (toujours hors ligne).

---

## 📂 Structure du projet

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
