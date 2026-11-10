# Suivi des dossiers

Application de suivi des dossiers administratifs (accusé de réception, retrait,
visa, retour) servie directement dans l'interface de Home Assistant, avec sa
propre base SQLite persistante.

## Installation

Voir la section **Add-on Home Assistant** du README du projet, ou le guide
`INSTALLATION-HA.md` (étapes détaillées et points de blocage).

## Accès

Après le démarrage, l'application apparaît dans la barre latérale de Home
Assistant sous le nom **Dossiers** (ou via *Paramètres → Modules complémentaires
→ Suivi des dossiers → Ouvrir l'interface web*).

- Une seule session par utilisateur Home Assistant, sans configuration réseau.
- L'application conserve sa propre page de connexion : au premier lancement,
  utilisez le compte de démonstration **admin / admin**, puis créez vos propres
  utilisateurs et changez le mot de passe depuis l'onglet *Utilisateurs*.

## Données

- La base est le fichier **`/data/dossiers.db`**, le volume privé et persistant
  de l'add-on : elle survit aux redémarrages, aux mises à jour et aux
  réinstallations, et elle est incluse dans les **sauvegardes Home Assistant**
  (Paramètres → Système → Sauvegardes).
- Pour récupérer une base existante (par exemple celle d'une installation
  locale), déposez le fichier `dossiers.db` dans le dossier partagé **`/share`**
  (accessible avec l'add-on *Samba share* ou l'éditeur de fichiers), puis
  démarrez l'add-on : il l'importe automatiquement si `/data/dossiers.db` est
  encore absent. La copie n'est faite qu'une seule fois.
- Restauration complète : restaurez la sauvegarde Home Assistant de l'add-on.

## Notes techniques

- L'add-on sert l'interface sur le port interne `8000` (ingress Home Assistant) ;
  aucun port n'est publié sur le réseau par défaut.
- Aucune connexion à l'extérieur n'est nécessaire : l'application est
  entièrement autonome une fois installée.
- Architectures prises en charge : `amd64` (PC, NUC, VM) et `aarch64`
  (Raspberry Pi 4/5, Green, Yellow).
- Pour repartir d'une base vide, restaurez une sauvegarde antérieure de
  l'add-on ; le compte de démonstration `admin` est alors recréé s'il manque.
