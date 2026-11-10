"""Helpers SQLite, schéma et règles métier de l'application de suivi des dossiers.

La base est un simple fichier (data/dossiers.db par défaut), donc la sauvegarde
consiste à copier ce seul fichier.  Tout l'état, y compris les compteurs de
numérotation par type, vit dans ce fichier et survit donc aux redémarrages.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

import chemins

BASE_DIR = chemins.HOME_DIR
DATA_DIR = chemins.chemin_donnees()
DB_PATH = os.environ.get("DOSSIER_DB_PATH") or os.path.join(DATA_DIR, "dossiers.db")

# ---------------------------------------------------------------------------
# Règles métier
# ---------------------------------------------------------------------------


class NumberingRangeExhausted(Exception):
    """Levée quand la plage de numéros d'un type de dossier est épuisée."""


# Les six types de documents, dans l'ordre d'affichage.  Chaque type possède sa
# propre plage de numéros et son propre compteur ; les compteurs sont stockés
# dans la table `counters`, donc la numérotation continue de croître et n'est
# jamais remise à zéro par un redémarrage.
#
# La plage ne peut pas être dépassée : une fois le dernier numéro attribué, la
# création d'un nouveau dossier de ce type est refusée.
NUMBERING_RULES: dict[str, dict[str, object]] = {
    "Affichage": {"start": 1, "end": 200},
    "Personnel": {"start": 201, "end": 400},
    "Autres": {"start": 401, "end": 600},
    "Marché": {"start": 601, "end": 800},
    "Décision": {"start": 801, "end": 1000},
    "DEF/TEF": {"start": 1001, "end": None},  # pas de plafond
}

# Types valides (source unique de vérité : les contraintes CHECK du schéma sont
# construites à partir de cette liste, elle-même dérivée des règles ci-dessus).
DOSSIER_TYPES = list(NUMBERING_RULES)
# Le statut décrit l'avancement du dossier ; l'état décrit sa présence physique
# (reçu dans les services ou retiré).  Un nouveau dossier démarre à l'état
# « Reçu » et au statut « En cours », tous deux modifiables manuellement.
DOSSIER_STATUSES = ["En cours", "Visé", "Rejeté", "Retour"]
DOSSIER_STATES = ["Reçu", "Retiré"]
DEFAULT_STATUS = "En cours"
DEFAULT_STATE = "Reçu"
# Rôles disponibles.  Le MVP n'expose que le rôle administrateur, mais la
# colonne existe pour les rôles à venir.
USER_ROLES = ["admin"]


def format_reference(number: int) -> str:
    """Numéro de dossier sur trois chiffres minimum (001, 002, …, 1000)."""
    return f"{number:03d}"


# Listes littérales SQL pour les contraintes CHECK (types, états, statuts).
_TYPE_SQL_LIST = ", ".join(f"'{t}'" for t in DOSSIER_TYPES)
_STATUS_SQL_LIST = ", ".join(f"'{s}'" for s in DOSSIER_STATUSES)
_STATE_SQL_LIST = ", ".join(f"'{s}'" for s in DOSSIER_STATES)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'admin',
    actif         INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dossiers (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_number   TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    type               TEXT NOT NULL CHECK (type IN ({_TYPE_SQL_LIST})),
    state              TEXT NOT NULL DEFAULT '{DEFAULT_STATE}'
                       CHECK (state IN ({_STATE_SQL_LIST})),
    status             TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}'
                       CHECK (status IN ({_STATUS_SQL_LIST})),
    created_date       TEXT NOT NULL,
    withdrawal_date    TEXT,
    withdrawn_by       TEXT,
    observation        TEXT,
    verifier_id        INTEGER NOT NULL REFERENCES users(id),
    parent_dossier_id  INTEGER REFERENCES dossiers(id) ON DELETE SET NULL,
    created_at         TEXT,
    updated_at         TEXT,
    deleted_at         TEXT
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    applicable_dossier_type TEXT NOT NULL
                            CHECK (applicable_dossier_type IN ({_TYPE_SQL_LIST})),
    is_mandatory            INTEGER NOT NULL DEFAULT 0,
    UNIQUE (name, applicable_dossier_type)
);

CREATE TABLE IF NOT EXISTS remarks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id   INTEGER NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL,
    author_id    INTEGER NOT NULL REFERENCES users(id),
    date         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS counters (
    type        TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dossiers_type ON dossiers(type);
CREATE INDEX IF NOT EXISTS idx_dossiers_status ON dossiers(status);
CREATE INDEX IF NOT EXISTS idx_dossiers_verifier ON dossiers(verifier_id);
CREATE INDEX IF NOT EXISTS idx_remarks_dossier ON remarks(dossier_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_type ON checkpoints(applicable_dossier_type);
"""


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------


@contextmanager
def get_db():
    """Ouvre une connexion courte.

    Le mode autocommit (isolation_level=None) est utilisé : chaque instruction
    est atomique, et les sections multi-instructions ouvrent une transaction
    explicite quand nécessaire (voir create_dossier dans main.py).
    """
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    """Aligne une base existante sur le schéma courant (sans perdre les données)."""
    user_columns = _columns(conn, "users")
    if user_columns and ("email" in user_columns or "role" not in user_columns):
        # Ancienne table avec email : reconstruction à l'identique, les comptes
        # existants deviennent administrateurs actifs.  Les instructions sont
        # exécutées une à une : executescript() validerait la transaction
        # implicitement.
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in (
                "DROP TABLE IF EXISTS users_new",
                """
                CREATE TABLE users_new (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    display_name  TEXT NOT NULL,
                    role          TEXT NOT NULL DEFAULT 'admin',
                    actif         INTEGER NOT NULL DEFAULT 1,
                    created_at    TEXT NOT NULL
                )
                """,
                "INSERT INTO users_new (id, username, password_hash, display_name, role, actif, created_at) "
                "SELECT id, username, password_hash, display_name, 'admin', 1, created_at FROM users",
                "DROP TABLE users",
                "ALTER TABLE users_new RENAME TO users",
            ):
                conn.execute(statement)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
        user_columns = _columns(conn, "users")

    dossier_columns = _columns(conn, "dossiers")
    for column, definition in (
        ("observation", "TEXT"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
        ("deleted_at", "TEXT"),
    ):
        if dossier_columns and column not in dossier_columns:
            conn.execute(f"ALTER TABLE dossiers ADD COLUMN {column} {definition}")

    # Colonne « state » (état) : l'ancienne contrainte CHECK du statut ne peut
    # pas être modifiée sur place, la table est donc reconstruite une seule
    # fois.  Les anciens statuts « Reçu » / « Retiré » deviennent l'état du
    # dossier, avec le statut « En cours ».
    if dossier_columns and "state" not in dossier_columns:
        _rebuild_dossiers(conn)

    # La date de visa devient la date de retrait, et le nom de la personne qui
    # retire le dossier est conservé.
    dossier_columns = _columns(conn, "dossiers")
    if dossier_columns and "withdrawal_date" not in dossier_columns:
        _rebuild_withdrawal(conn)

    # Le statut « Retour » a été ajouté : la contrainte CHECK, figée dans le
    # schéma SQLite, impose de reconstruire la table sur les bases existantes.
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'dossiers'"
    ).fetchone()
    if table_sql and table_sql[0] and "'Retour'" not in table_sql[0]:
        _rebuild_withdrawal(conn)

    # Le verdict des remarques a été retiré : seule l'observation libre reste.
    if "verdict" in _columns(conn, "remarks"):
        _rebuild_remarks(conn)


def _rebuild_dossiers(conn: sqlite3.Connection) -> None:
    """Reconstruit `dossiers` avec la colonne state et les nouveaux statuts."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for statement in (
            "DROP TABLE IF EXISTS dossiers_new",
            f"""
            CREATE TABLE dossiers_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_number   TEXT NOT NULL UNIQUE,
                name               TEXT NOT NULL,
                type               TEXT NOT NULL CHECK (type IN ({_TYPE_SQL_LIST})),
                state              TEXT NOT NULL DEFAULT '{DEFAULT_STATE}'
                                   CHECK (state IN ({_STATE_SQL_LIST})),
                status             TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}'
                                   CHECK (status IN ({_STATUS_SQL_LIST})),
                created_date       TEXT NOT NULL,
                withdrawal_date    TEXT,
                withdrawn_by       TEXT,
                observation        TEXT,
                verifier_id        INTEGER NOT NULL REFERENCES users(id),
                parent_dossier_id  INTEGER REFERENCES dossiers_new(id) ON DELETE SET NULL,
                created_at         TEXT,
                updated_at         TEXT,
                deleted_at         TEXT
            )
            """,
            "INSERT INTO dossiers_new (id, reference_number, name, type, state, status, "
            "created_date, withdrawal_date, withdrawn_by, observation, verifier_id, "
            "parent_dossier_id, created_at, updated_at, deleted_at) "
            "SELECT id, reference_number, name, type, "
            "CASE WHEN status = 'Retiré' THEN 'Retiré' ELSE 'Reçu' END, "
            "CASE WHEN status IN ('Visé', 'Rejeté') THEN status ELSE 'En cours' END, "
            "created_date, validation_date, NULL, observation, verifier_id, "
            "parent_dossier_id, created_at, updated_at, deleted_at FROM dossiers",
            "DROP TABLE dossiers",
            "ALTER TABLE dossiers_new RENAME TO dossiers",
            "CREATE INDEX IF NOT EXISTS idx_dossiers_type ON dossiers(type)",
            "CREATE INDEX IF NOT EXISTS idx_dossiers_status ON dossiers(status)",
            "CREATE INDEX IF NOT EXISTS idx_dossiers_verifier ON dossiers(verifier_id)",
        ):
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_withdrawal(conn: sqlite3.Connection) -> None:
    """Reconstruit `dossiers` avec le schéma courant (colonnes et CHECK à jour).

    Utilisée pour la date de retrait comme pour l'ajout d'un nouveau statut.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        columns = _columns(conn, "dossiers")
        date_expr = (
            "withdrawal_date"
            if "withdrawal_date" in columns
            else "validation_date" if "validation_date" in columns else "NULL"
        )
        name_expr = "withdrawn_by" if "withdrawn_by" in columns else "NULL"
        for statement in (
            "DROP TABLE IF EXISTS dossiers_new",
            f"""
            CREATE TABLE dossiers_new (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_number   TEXT NOT NULL UNIQUE,
                name               TEXT NOT NULL,
                type               TEXT NOT NULL CHECK (type IN ({_TYPE_SQL_LIST})),
                state              TEXT NOT NULL DEFAULT '{DEFAULT_STATE}'
                                   CHECK (state IN ({_STATE_SQL_LIST})),
                status             TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}'
                                   CHECK (status IN ({_STATUS_SQL_LIST})),
                created_date       TEXT NOT NULL,
                withdrawal_date    TEXT,
                withdrawn_by       TEXT,
                observation        TEXT,
                verifier_id        INTEGER NOT NULL REFERENCES users(id),
                parent_dossier_id  INTEGER REFERENCES dossiers_new(id) ON DELETE SET NULL,
                created_at         TEXT,
                updated_at         TEXT,
                deleted_at         TEXT
            )
            """,
            "INSERT INTO dossiers_new (id, reference_number, name, type, state, status, "
            "created_date, withdrawal_date, withdrawn_by, observation, verifier_id, "
            "parent_dossier_id, created_at, updated_at, deleted_at) "
            "SELECT id, reference_number, name, type, state, status, created_date, "
            f"{date_expr}, {name_expr}, observation, verifier_id, "
            "parent_dossier_id, created_at, updated_at, deleted_at FROM dossiers",
            "DROP TABLE dossiers",
            "ALTER TABLE dossiers_new RENAME TO dossiers",
            "CREATE INDEX IF NOT EXISTS idx_dossiers_type ON dossiers(type)",
            "CREATE INDEX IF NOT EXISTS idx_dossiers_status ON dossiers(status)",
            "CREATE INDEX IF NOT EXISTS idx_dossiers_verifier ON dossiers(verifier_id)",
        ):
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_remarks(conn: sqlite3.Connection) -> None:
    """Reconstruit `remarks` sans la colonne verdict (observation seule)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for statement in (
            "DROP TABLE IF EXISTS remarks_new",
            """
            CREATE TABLE remarks_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                dossier_id   INTEGER NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
                comment_text TEXT NOT NULL,
                author_id    INTEGER NOT NULL REFERENCES users(id),
                date         TEXT NOT NULL
            )
            """,
            "INSERT INTO remarks_new (id, dossier_id, comment_text, author_id, date) "
            "SELECT id, dossier_id, comment_text, author_id, date FROM remarks",
            "DROP TABLE remarks",
            "ALTER TABLE remarks_new RENAME TO remarks",
            "CREATE INDEX IF NOT EXISTS idx_remarks_dossier ON remarks(dossier_id)",
        ):
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    """Crée les tables et les compteurs par type s'ils n'existent pas."""
    with get_db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        for dossier_type, rule in NUMBERING_RULES.items():
            conn.execute(
                "INSERT OR IGNORE INTO counters(type, last_number) VALUES (?, ?)",
                (dossier_type, int(rule["start"]) - 1),
            )


def _range_end(dossier_type: str) -> int | None:
    end = NUMBERING_RULES[dossier_type]["end"]
    return int(end) if end is not None else None


def next_reference_number(conn: sqlite3.Connection, dossier_type: str) -> str:
    """Attribue le numéro suivant pour un type de dossier.

    Doit être appelé dans une transaction ouverte avec l'INSERT du dossier,
    pour qu'un numéro ne soit jamais distribué deux fois.  Le compteur est mis
    à jour sur place : l'attribution est atomique et persistante, un
    redémarrage ne le remet pas à zéro.

    Lève NumberingRangeExhausted quand la plage du type est épuisée.
    """
    rule = NUMBERING_RULES[dossier_type]
    row = conn.execute(
        "SELECT last_number FROM counters WHERE type = ?", (dossier_type,)
    ).fetchone()
    last = row["last_number"] if row else int(rule["start"]) - 1
    if row is None:  # ligne de compteur absente sur une base neuve
        conn.execute(
            "INSERT OR IGNORE INTO counters(type, last_number) VALUES (?, ?)",
            (dossier_type, last),
        )

    end = _range_end(dossier_type)
    if end is not None and last >= end:
        raise NumberingRangeExhausted(
            f"La plage de numéros du type « {dossier_type} » est épuisée "
            f"(dernier numéro possible : {format_reference(end)})."
        )

    row = conn.execute(
        "UPDATE counters SET last_number = last_number + 1 "
        "WHERE type = ? RETURNING last_number",
        (dossier_type,),
    ).fetchone()
    return format_reference(int(row["last_number"]))


def reference_preview(dossier_type: str, conn: sqlite3.Connection | None = None) -> str | None:
    """Numéro que recevrait le prochain dossier de ce type (None si épuisé)."""
    rule = NUMBERING_RULES[dossier_type]
    if conn is None:
        with get_db() as own_conn:
            return reference_preview(dossier_type, own_conn)
    row = conn.execute(
        "SELECT last_number FROM counters WHERE type = ?", (dossier_type,)
    ).fetchone()
    last = row["last_number"] if row else int(rule["start"]) - 1
    nxt = last + 1
    end = _range_end(dossier_type)
    if end is not None and nxt > end:
        return None
    return format_reference(nxt)
