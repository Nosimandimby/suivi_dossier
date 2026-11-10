# Installer l'add-on « Suivi des dossiers » sur Home Assistant

Guide pas à pas, de la copie des fichiers au premier dossier saisi, avec les
points de blocage courants et leur solution.

> Les écrans sont décrits par leur contenu réel (titres, boutons, emplacements)
> plutôt que par des captures : une capture de Home Assistant ne peut être prise
> que sur votre installation. Chaque étape indique donc précisément **ce que
> vous devez voir** pour savoir que vous êtes au bon endroit.

---

## 0. Prérequis

| Élément | Nécessaire |
|---|---|
| Type d'installation | **Home Assistant OS** ou **Supervised** (l'installation « Container » n'a pas de boutique d'add-ons) |
| Version | Une version récente de Home Assistant (2024.1+ ; `arch`, `ingress` et `map` sont des clés stables) |
| Matériel | `amd64` (PC, NUC, VM, HA Yellow) ou `aarch64` (Raspberry Pi 4/5, HA Green) — **armv7 / armhf non supportés** |
| Accès fichiers | L'add-on **Samba share** *ou* **Advanced SSH & Web Terminal** (les deux s'installent depuis la boutique officielle) |
| Réseau | La machine HA doit pouvoir joindre `ghcr.io` et PyPI pendant la construction (phase de build uniquement) |

Vous avez besoin du dossier **`suivi_dossiers/`** de ce projet (pas de toute
l'application) :

```
suivi_dossiers/
├── config.yaml
├── Dockerfile
├── run.sh
├── DOCS.md
├── icon.png
├── logo.png
└── app/          ← main.py, database.py, seed.py, chemins.py, requirements.txt, static/
```

Si `app/` est vide ou absent : lancez `./synchroniser-addon.sh` sur la machine
où se trouve le projet avant de copier.

---

## Méthode A — installation locale (sans GitHub)

C'est la méthode la plus rapide et celle qui marche hors ligne (hors build).

### A1. Activer le mode avancé

**Profil** (en bas de la barre latérale) → onglet **Mode avancé** → activer.

*Vous devez voir* : un nouvel onglet **Modules complémentaires** apparaît dans
**Paramètres**, et le menu ⋮ de la boutique propose désormais
« Vérifier les mises à jour ».

### A2. Copier le dossier dans `/addons`

Avec **Samba share**, le dossier s'appelle `addons` à la racine du partage
réseau. Avec **Advanced SSH & Web Terminal**, connectez-vous puis :

```bash
# vérifier que le dossier n'existe pas déjà
ls /addons

# copier le dossier depuis votre ordinateur (ou le recréer sur place)
# le résultat doit être : /addons/suivi_dossiers/config.yaml
```

À la fin, **`/addons/suivi_dossiers/config.yaml` doit exister** : c'est le seul
fichier que Home Assistant cherche pour détecter un add-on local. Un niveau de
trop (`/addons/suivi_dossiers/suivi_dossiers/config.yaml`) est la cause n°1
d'add-on invisible.

### A3. Faire apparaître l'add-on dans la boutique

**Paramètres → Modules complémentaires → Boutique**, puis menu **⋮** (en haut à
droite) → **Vérifier les mises à jour** (parfois « Recharger »).

*Vous devez voir* : une nouvelle section **Modules complémentaires locaux** en
bas de la boutique, avec la carte **Suivi des dossiers** et son icône de dossier.

### A4. Installer

Cliquez sur la carte → bouton **Installer**.

*Vous devez voir* : un panneau de progression avec les étapes successives
(`Fetching base image`, `Building image`, `Installing…`). Le premier build prend
**3 à 10 minutes** selon la machine (téléchargement de l'image de base Python
Alpine + des roues FastAPI/Uvicorn).

### A5. Démarrer

Onglet **Démarrer** → **Démarrer** (l'add-on est déjà réglé sur
« Démarrer au démarrage » via `boot: auto`, et **Afficher dans la barre
latérale** est actif via `ingress`).

*Vous devez voir dans l'onglet **Journaux*** :

```
[INFO] Suivi des dossiers - démarrage
[INFO] Base de données : /data/dossiers.db
  Suivi des dossiers
  Ouvrir http://0.0.0.0:8000 dans le navigateur
  Connexion de démonstration : admin / admin
```

Puis, dans la barre latérale de Home Assistant, une nouvelle entrée
**Dossiers** (icône dossier avec personne).

---

## Méthode B — dépôt d'add-ons (mises à jour proposées automatiquement)

### B1. Publier le dépôt

Poussez ce dossier du projet (avec `repository.yaml` à la racine et
`suivi_dossiers/` juste en dessous) sur GitHub, Gitea, GitLab…

Structure attendue du dépôt :

```
repository.yaml
suivi_dossiers/
    config.yaml
    Dockerfile
    ...
```

### B2. Ajouter le dépôt

**Paramètres → Modules complémentaires → Boutique → ⋮ → Dépôts** → collez
l'URL du dépôt (`https://github.com/<compte>/<depot>`) → **Ajouter**.

*Vous devez voir* : le dépôt listé dans les trois points du menu, et sa section
d'add-ons dans la boutique. Installez et démarrez comme en A4–A5.

### B3. Mettre à jour plus tard

1. Sur la machine de développement : modifier le code puis
   `./synchroniser-addon.sh`.
2. **Incrémenter `version:`** dans `suivi_dossiers/config.yaml` (par exemple
   `1.0.0` → `1.0.1`) : sans changement de version, Home Assistant ne propose
   aucune mise à jour.
3. Publier (commit + push).
4. Dans HA : boutique → ⋮ → **Vérifier les mises à jour** → **Mettre à jour**.

La base `/data/dossiers.db` est conservée pendant la mise à jour.

---

## Après l'installation

### Première connexion

Ouvrez **Dossiers** dans la barre latérale → page de connexion de
l'application → **admin** / **admin**.

Puis, immédiatement : onglet **Utilisateurs** → modifier `admin` → nouveau mot
de passe. Le compte de démonstration reste sinon actif pour tout utilisateur
ayant accès à Home Assistant.

### Récupérer vos données existantes (les 4 dossiers actuels)

L'import ne se fait **qu'une seule fois**, au premier démarrage, et seulement si
`/data/dossiers.db` n'existe pas encore.

1. Arrêtez l'add-on s'il tourne déjà.
2. Copiez votre fichier `data/dossiers.db` (base de l'application locale) dans
   le dossier partagé **`/share`** de Home Assistant, sous le nom exact
   `dossiers.db` (via Samba ou l'éditeur de fichiers).
3. Démarrez l'add-on.

*Vous devez voir dans les journaux* :

```
[INFO] Base existante importée depuis /share/dossiers.db
[INFO] Base de données : /data/dossiers.db
```

Vérification : le tableau de bord affiche le nombre de dossiers attendu. Si
vous voyez la base de démonstration à la place, c'est que `/data/dossiers.db`
existait déjà (voir « Base vide ou base de démo inattendue » ci-dessous).

### Sauvegardes

**Paramètres → Système → Sauvegardes** : l'add-on et son `/data` sont inclus
dans les sauvegardes complètes. Pour une sauvegarde partielle, sélectionnez
uniquement **Suivi des dossiers**. La restauration remet la base et les comptes
en l'état de la sauvegarde.

---

## Points de blocage courants

| Symptôme | Cause | Solution |
|---|---|---|
| La carte **Suivi des dossiers** n'apparaît pas dans la boutique | Dossier mal placé, ou boutique non rechargée | Vérifier que `/addons/suivi_dossiers/config.yaml` existe (un seul niveau), puis ⋮ → **Vérifier les mises à jour**. Redémarrer Home Assistant si besoin. |
| Le menu ⋮ ne propose pas « Vérifier les mises à jour » | Mode avancé désactivé | **Profil → Mode avancé** |
| Boutique totalement absente | Installation en mode « Container » (Docker seul) | Il faut HA OS ou Supervised ; sinon lancer l'app normalement (`./suivi-dossiers`) ou en Docker manuel |
| Échec au build : `no matching manifest for linux/arm/v7` | Architecture non supportée | L'add-on ne fonctionne que sur `amd64` et `aarch64` |
| Échec au build : timeout / `ghcr.io` ou `pypi.org` injoignable | Filtrage DNS, proxy, Pi-hole, pas d'accès Internet | Autoriser `ghcr.io` et `files.pythonhosted.org` pour la machine HA, relancer |
| Échec au build : `Could not find a version that satisfies the requirement …` | Roue indisponible pour cette architecture/python | Vérifier `suivi_dossiers/app/requirements.txt` ; le build utilise Python 3.13 Alpine (musl) |
| `BUILD_FROM` inconnu / `FROM` manquant | Anciennes configs d'add-on | Le `Dockerfile` de ce projet contient un `FROM` explicite, ne pas le remplacer par `BUILD_FROM` |
| L'add-on démarre puis s'arrête aussitôt | Port 8000 déjà pris, ou `/data` non inscriptible | Consulter l'onglet **Journaux** : la dernière trace indique la cause (`address already in use`, `Permission denied`) |
| Page blanche ou style absent | Ancienne version du front (URL absolues) ou cache | Vider le cache du navigateur / recharger avec `Ctrl+F5` ; `static/index.html` doit référencer `static/style.css?v=10` |
| Erreurs 404 sur `/api/...` ou `/static/...` | Accès par une URL directe au lieu de l'ingress | Toujours passer par la barre latérale **Dossiers** (l'add-on n'expose aucun port) |
| L'interface se déconnecte sans cesse | Jeton expiré, onglet dupliqué | Recharger la page, se reconnecter |
| **Base de démo au lieu de mes données** | `/data/dossiers.db` existait déjà : l'import a été ignoré | Restaurer une sauvegarde, ou repartir d'une installation propre (désinstaller/réinstaller l'add-on après avoir remis `dossiers.db` dans `/share`) |
| `/share/dossiers.db` introuvable | Dossier partagé non activé | Installer l'add-on **Samba share** et déposer le fichier à la racine du partage ; l'add-on monte `/share` en lecture seule (`map: share`) |
| Le panneau **Dossiers** manque après l'installation | Panneau non rafraîchi | Recharger Home Assistant (`Ctrl+F5` sur l'interface), vérifier `ingress: true` et `panel_title` dans `config.yaml` |
| « Add-on non pris en charge » sur un vieux HA | `arch`/`ingress` récents | Mettre à jour Home Assistant, ou adapter `arch` dans `config.yaml` |

---

## Vérifications finales (checklist)

- [ ] La boutique affiche l'add-on dans **Modules complémentaires locaux**
- [ ] La version affichée est `1.0.0`
- [ ] L'onglet **Journaux** ne contient aucun `Traceback`
- [ ] `[INFO] Base de données : /data/dossiers.db` apparaît au démarrage
- [ ] L'entrée **Dossiers** est présente dans la barre latérale
- [ ] La connexion `admin` / `admin` fonctionne
- [ ] Le mot de passe `admin` a été changé
- [ ] Le tableau de bord affiche les compteurs et la liste des dossiers
- [ ] (si import) `Base existante importée depuis /share/dossiers.db` dans les journaux
- [ ] Une sauvegarde Home Assistant incluant l'add-on a été lancée
- [ ] Après redémarrage de l'add-on, les dossiers sont toujours là
