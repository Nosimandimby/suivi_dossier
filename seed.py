"""Script de peuplement : points de contrôle par type et compte de démonstration.

Sûr à exécuter plusieurs fois (idempotent).  Lancement direct :

    python seed.py

Il est aussi appelé automatiquement au démarrage de l'application, pour qu'une
simple commande `python main.py` suffise.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

import database as db

# ---------------------------------------------------------------------------
# Compte administrateur par défaut (connexion par nom d'utilisateur)
# ---------------------------------------------------------------------------
# (nom_utilisateur, mot_de_passe, nom_affiché, rôle, actif)
SEED_USERS = [
    ("admin", "admin", "Admin", "admin", 1),
]

# ---------------------------------------------------------------------------
# Catalogue des points de contrôle : les contrôles varient selon le type.
# (nom, description, type_applicable, obligatoire)
# Cinq contrôles par type : les obligatoires en premier dans l'interface.
# ---------------------------------------------------------------------------
SEED_CHECKPOINTS = [
    # --- Affichage ---------------------------------------------------------
    (
        "Complétude du dossier",
        "Toutes les pages du dossier sont présentes et dans le bon ordre.",
        "Affichage",
        1,
    ),
    (
        "Cohérence des références",
        "Les numéros de référence internes correspondent aux entrées du registre.",
        "Affichage",
        1,
    ),
    (
        "Signatures",
        "Le responsable a signé chaque page d'approbation.",
        "Affichage",
        1,
    ),
    (
        "Lisibilité des pages",
        "Les pages numérisées sont lisibles ; les pages illisibles sont rescannées.",
        "Affichage",
        0,
    ),
    (
        "Enregistrement aux archives",
        "Le dossier est inscrit au registre central des documents.",
        "Affichage",
        0,
    ),
    # --- Personnel ---------------------------------------------------------
    (
        "Complétude du dossier",
        "Toutes les pièces exigées sont présentes et classées dans l'ordre.",
        "Personnel",
        1,
    ),
    (
        "Signatures",
        "Le responsable a signé chaque page d'approbation.",
        "Personnel",
        1,
    ),
    (
        "Confidentialité des données",
        "Les données personnelles sont conservées de façon confidentielle et l'accès est restreint.",
        "Personnel",
        1,
    ),
    (
        "Respect des délais de classement",
        "Les pièces ont été classées dans le délai de conservation applicable.",
        "Personnel",
        0,
    ),
    (
        "Enregistrement au registre du personnel",
        "Le dossier est inscrit au registre des archives du personnel.",
        "Personnel",
        0,
    ),
    # --- Autres ------------------------------------------------------------
    (
        "Complétude du dossier",
        "Toutes les pages du dossier sont présentes et dans le bon ordre.",
        "Autres",
        1,
    ),
    (
        "Cohérence des références",
        "Les numéros de référence internes correspondent aux entrées du registre.",
        "Autres",
        1,
    ),
    (
        "Signatures",
        "Le responsable a signé chaque page d'approbation.",
        "Autres",
        1,
    ),
    (
        "Lisibilité des pages",
        "Les pages numérisées sont lisibles ; les pages illisibles sont rescannées.",
        "Autres",
        0,
    ),
    (
        "Enregistrement aux archives",
        "Le dossier est inscrit au registre central des documents.",
        "Autres",
        0,
    ),
    # --- Marché ------------------------------------------------------------
    (
        "Signature du contrat",
        "Les deux parties ont signé le contrat à tous les endroits requis.",
        "Marché",
        1,
    ),
    (
        "Qualification du fournisseur",
        "Le dossier de qualification du fournisseur est complet et à jour.",
        "Marché",
        1,
    ),
    (
        "Validité des dates",
        "Les certificats et le contrat lui-même sont dans leur période de validité.",
        "Marché",
        1,
    ),
    (
        "Couverture d'assurance",
        "L'attestation d'assurance responsabilité couvre la période de livraison.",
        "Marché",
        0,
    ),
    (
        "Historique des révisions",
        "Tous les avenants sont joints ; les versions remplacées sont retirées.",
        "Marché",
        0,
    ),
    # --- Décision ----------------------------------------------------------
    (
        "Compétence de l'autorité",
        "La décision est prise par l'autorité compétente dans le cadre de ses pouvoirs.",
        "Décision",
        1,
    ),
    (
        "Cohérence des références",
        "Les numéros de référence internes correspondent aux entrées du registre.",
        "Décision",
        1,
    ),
    (
        "Notification des parties",
        "Toutes les parties concernées ont été informées de la décision.",
        "Décision",
        1,
    ),
    (
        "Lisibilité des pages",
        "Les pages numérisées sont lisibles ; les pages illisibles sont rescannées.",
        "Décision",
        0,
    ),
    (
        "Enregistrement aux archives",
        "Le dossier est inscrit au registre central des documents.",
        "Décision",
        0,
    ),
    # --- DEF/TEF -----------------------------------------------------------
    (
        "Autorisations réglementaires",
        "Les autorisations et permis requis sont joints au dossier.",
        "DEF/TEF",
        1,
    ),
    (
        "Évaluation des risques",
        "L'évaluation des risques est revue et validée par le responsable.",
        "DEF/TEF",
        1,
    ),
    (
        "Rapport d'inspection finale",
        "Le rapport d'inspection finale est joint et ne comporte pas de réserve ouverte.",
        "DEF/TEF",
        1,
    ),
    (
        "Procès-verbal de remise",
        "Le procès-verbal de remise est signé par les deux parties.",
        "DEF/TEF",
        1,
    ),
    (
        "Dossiers de formation des opérateurs",
        "Les attestations de formation des opérateurs concernés sont au dossier.",
        "DEF/TEF",
        0,
    ),
]


def hash_password(password: str, salt: str | None = None) -> str:
    """Empreinte PBKDF2-SHA256, bibliothèque standard uniquement."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    ).hex()
    return f"{salt}${digest}"


def run() -> None:
    """Insère les comptes de démonstration et le catalogue de contrôles."""
    created_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    with db.get_db() as conn:
        for username, password, display_name, role, actif in SEED_USERS:
            conn.execute(
                "INSERT OR IGNORE INTO users "
                "(username, password_hash, display_name, role, actif, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    username,
                    hash_password(password),
                    display_name,
                    role,
                    actif,
                    created_at,
                ),
            )
        for name, description, applicable_type, is_mandatory in SEED_CHECKPOINTS:
            conn.execute(
                "INSERT OR IGNORE INTO checkpoints "
                "(name, description, applicable_dossier_type, is_mandatory) "
                "VALUES (?, ?, ?, ?)",
                (name, description, applicable_type, is_mandatory),
            )


if __name__ == "__main__":
    db.init_db()
    run()
    with db.get_db() as conn:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        points = conn.execute("SELECT COUNT(*) AS n FROM checkpoints").fetchone()["n"]
    print(f"Peuplement terminé : {users} utilisateur(s), {points} points de contrôle -> {db.DB_PATH}")
