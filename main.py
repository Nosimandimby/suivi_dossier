"""Suivi des dossiers - backend FastAPI servant une interface HTML/JS simple.

Lancement :  python main.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database as db
import seed
import chemins
from chemins import RESSOURCES_DIR
from database import (
    DEFAULT_STATE,
    DEFAULT_STATUS,
    DOSSIER_STATES,
    DOSSIER_STATUSES,
    DOSSIER_TYPES,
    NUMBERING_RULES,
    ROLE_ADMIN,
    ROLE_DELEGUE,
    ROLE_VERIFICATEUR,
    USER_ROLES,
    get_db,
    get_users_db,
)

BASE_DIR = chemins.HOME_DIR
STATIC_DIR = os.path.join(RESSOURCES_DIR, "static")
SESSION_DAYS = 30

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,50}$")

# Les comptes étant dans une autre base, le vérificateur n'est plus joint :
# son identifiant est résolu en nom par _user_names().
DOSSIER_SELECT = """
    SELECT d.*,
           p.reference_number AS parent_reference,
           p.name             AS parent_name
    FROM dossiers d
    LEFT JOIN dossiers p ON p.id = d.parent_dossier_id
"""


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

app = FastAPI(title="Suivi des dossiers", version="1.0.0")

db.init_db()   # tables + compteurs de numérotation (persistants)
seed.run()     # compte de démonstration + points de contrôle (idempotent)

os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def _now() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def _today() -> str:
    return dt.date.today().isoformat()


def _expiry() -> str:
    return (dt.datetime.now() + dt.timedelta(days=SESSION_DAYS)).replace(
        microsecond=0
    ).isoformat()


def _parse_date(value: str) -> str:
    """Valide une date AAAA-MM-JJ et la renvoie normalisée."""
    try:
        return dt.date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Date invalide : utilisez le format AAAA-MM-JJ.",
        )


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    candidate = seed.hash_password(password, salt)
    return hmac.compare_digest(candidate, stored)


def _public_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "actif": bool(row["actif"]),
    }


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Résout l'utilisateur connecté à partir du jeton Bearer. Le vérificateur
    d'un dossier vient toujours d'ici, jamais du corps de la requête."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non connecté")
    token = authorization[7:].strip()
    # Comptes et sessions vivent dans leur propre base.
    with get_users_db() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.display_name, u.role, u.actif "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ? AND u.actif = 1",
            (token, _now()),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=401, detail="Session expirée, veuillez vous reconnecter"
        )
    return dict(row)


# ---------------------------------------------------------------------------
# Rôles et permissions
# ---------------------------------------------------------------------------
#
# - admin        : tout (dossiers, comptes, import, réinitialisation)
# - Vérificateur : tout sauf la gestion des comptes et la réinitialisation
# - Délégué      : consultation seule, aucune écriture
#
# Les droits sont vérifiés ici, côté serveur : masquer un bouton dans
# l'interface ne protège rien.


def is_admin(user: dict) -> bool:
    return user["role"] == ROLE_ADMIN


def can_write(user: dict) -> bool:
    """Un délégué lit seulement ; les autres rôles peuvent modifier les données."""
    return user["role"] in (ROLE_ADMIN, ROLE_VERIFICATEUR)


def require_admin(user: dict = Depends(current_user)) -> dict:
    if not is_admin(user):
        raise HTTPException(
            status_code=403, detail="Action réservée à l'administrateur."
        )
    return user


def require_write(user: dict = Depends(current_user)) -> dict:
    if not can_write(user):
        raise HTTPException(
            status_code=403,
            detail="Votre rôle « Délégué » permet seulement la consultation.",
        )
    return user


def _user_out(row) -> dict:
    out = dict(row)
    out["actif"] = bool(out["actif"])
    out["dossier_count"] = out.get("dossier_count") or 0
    return out


def _checkpoint_out(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "applicable_dossier_type": row["applicable_dossier_type"],
        "is_mandatory": bool(row["is_mandatory"]),
    }


def _remark_out(row, author_name: str) -> dict:
    return {
        "id": row["id"],
        "dossier_id": row["dossier_id"],
        "comment_text": row["comment_text"],
        "author_id": row["author_id"],
        "author_name": author_name,
        "date": row["date"],
    }


def _user_names(ids) -> dict[int, str]:
    """Noms affichés des comptes, lus dans la base des utilisateurs.

    Les deux bases n'ont aucune jointure commune : les identifiants stockés
    dans les dossiers et les remarques sont résolus ici, en une requête.
    """
    ids = {int(i) for i in ids if i is not None}
    if not ids:
        return {}
    placeholders = ", ".join("?" * len(ids))
    with get_users_db() as conn:
        rows = conn.execute(
            f"SELECT id, display_name FROM users WHERE id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
    return {row["id"]: row["display_name"] for row in rows}


def _dossier_out(row, verifier_name: str) -> dict:
    keys = row.keys()
    return {
        "id": row["id"],
        "reference_number": row["reference_number"],
        "name": row["name"],
        "type": row["type"],
        "state": row["state"],
        "status": row["status"],
        "created_date": row["created_date"],
        "withdrawal_date": row["withdrawal_date"],
        "withdrawn_by": row["withdrawn_by"],
        "observation": row["observation"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
        "verifier_id": row["verifier_id"],
        "verifier_name": verifier_name,
        "parent_dossier_id": row["parent_dossier_id"],
        "parent_reference": row["parent_reference"] if "parent_reference" in keys else None,
        "parent_name": row["parent_name"] if "parent_name" in keys else None,
    }


def _dossiers_out(rows) -> list[dict]:
    noms = _user_names({row["verifier_id"] for row in rows})
    return [_dossier_out(row, noms.get(row["verifier_id"], "—")) for row in rows]


def _dossier_single_out(row) -> dict:
    return _dossiers_out([row])[0]


def _require_type(value: str) -> str:
    if value not in DOSSIER_TYPES:
        raise HTTPException(status_code=400, detail=f"Type de dossier inconnu : {value}")
    return value


def _require_status(value: str) -> str:
    if value not in DOSSIER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Statut inconnu : {value}")
    return value


def _require_state(value: str) -> str:
    if value not in DOSSIER_STATES:
        raise HTTPException(status_code=400, detail=f"État inconnu : {value}")
    return value


def _resolve_parent(conn, parent_id: int | None, dossier_id: int | None) -> int | None:
    """Valide la relation parent optionnelle (existe, pas soi-même, pas de cycle)."""
    if parent_id is None:
        return None
    if parent_id == dossier_id:
        raise HTTPException(
            status_code=400, detail="Un dossier ne peut pas être son propre parent"
        )
    if conn.execute(
        "SELECT 1 FROM dossiers WHERE id = ? AND deleted_at IS NULL", (parent_id,)
    ).fetchone() is None:
        raise HTTPException(status_code=400, detail="Dossier parent introuvable")
    seen: set[int] = {dossier_id} if dossier_id is not None else set()
    current: int | None = parent_id
    while current is not None:
        if current in seen:
            raise HTTPException(
                status_code=400, detail="La sélection du parent créerait un cycle"
            )
        seen.add(current)
        row = conn.execute(
            "SELECT parent_dossier_id FROM dossiers WHERE id = ?", (current,)
        ).fetchone()
        current = row["parent_dossier_id"] if row else None
    return parent_id


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------


class LoginIn(BaseModel):
    identity: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@app.post("/api/login")
def login(body: LoginIn) -> dict:
    identity = body.identity.strip()
    with get_users_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (identity,),
        ).fetchone()
        if row is None or not verify_password(body.password, row["password_hash"]):
            raise HTTPException(
                status_code=401, detail="Identifiant ou mot de passe incorrect"
            )
        if not row["actif"]:
            raise HTTPException(status_code=403, detail="Ce compte est désactivé")
        token = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token, row["id"], _now(), _expiry()),
        )
    return {"token": token, "user": _public_user(row)}


@app.post("/api/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        with get_users_db() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token = ?", (authorization[7:].strip(),)
            )
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@app.put("/api/me/password")
def change_my_password(
    body: PasswordChangeIn, user: dict = Depends(current_user)
) -> dict:
    """Chaque utilisateur change son propre mot de passe.

    Aucun rôle n'est requis : la modification ne porte que sur le compte de la
    session, et le mot de passe actuel est demandé pour qu'une session laissée
    ouverte ne suffise pas à verrouiller le compte.
    """
    nouveau = body.new_password
    if len(nouveau) < 4:
        raise HTTPException(
            status_code=400,
            detail="Le mot de passe doit contenir au moins 4 caractères",
        )
    with get_users_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
        if row is None or not verify_password(
            body.current_password, row["password_hash"]
        ):
            raise HTTPException(
                status_code=400, detail="Le mot de passe actuel est incorrect"
            )
        if body.current_password == nouveau:
            raise HTTPException(
                status_code=400,
                detail="Le nouveau mot de passe doit être différent de l'actuel",
            )
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (seed.hash_password(nouveau), user["id"]),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Métadonnées de référence
# ---------------------------------------------------------------------------


@app.get("/api/meta")
def meta(user: dict = Depends(current_user)) -> dict:
    with get_db() as conn:
        types = [
            {
                "value": t,
                "label": t,
                "start": NUMBERING_RULES[t]["start"],
                "end": NUMBERING_RULES[t]["end"],
                "next": db.reference_preview(t, conn),
            }
            for t in DOSSIER_TYPES
        ]
    return {
        "types": types,
        "statuses": DOSSIER_STATUSES,
        "default_status": DEFAULT_STATUS,
        "states": DOSSIER_STATES,
        "default_state": DEFAULT_STATE,
        "roles": USER_ROLES,
        # Droits du compte connecté : l'interface s'en sert pour masquer les
        # actions interdites, le serveur les vérifie de son côté.
        "permissions": {"admin": is_admin(user), "write": can_write(user)},
    }


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=4, max_length=200)
    role: str = "admin"
    actif: bool = True


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=200)
    role: str | None = None
    actif: bool | None = None


def _require_role(value: str) -> str:
    if value not in USER_ROLES:
        raise HTTPException(status_code=400, detail=f"Rôle inconnu : {value}")
    return value


USER_SELECT = """
    SELECT u.id, u.username, u.display_name, u.role, u.actif, u.created_at
    FROM users u
"""


def _dossier_counts_by_user() -> dict[int, int]:
    """Nombre de dossiers actifs par vérificateur (base des dossiers)."""
    with get_db() as conn:
        return {
            row["verifier_id"]: row["n"]
            for row in conn.execute(
                "SELECT verifier_id, COUNT(*) AS n FROM dossiers "
                "WHERE deleted_at IS NULL GROUP BY verifier_id"
            )
        }


@app.get("/api/users")
def list_users(user: dict = Depends(current_user)) -> list[dict]:
    with get_users_db() as conn:
        rows = conn.execute(
            USER_SELECT + " ORDER BY u.display_name COLLATE NOCASE"
        ).fetchall()
    counts = _dossier_counts_by_user()
    result = []
    for row in rows:
        item = _user_out(row)
        item["dossier_count"] = counts.get(row["id"], 0)
        result.append(item)
    return result


@app.post("/api/users", status_code=201)
def create_user(body: UserIn, user: dict = Depends(require_admin)) -> dict:
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="L'identifiant doit contenir 2 à 50 caractères : lettres, chiffres, point, tiret ou souligné.",
        )
    display_name = body.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Le nom affiché est obligatoire")
    role = _require_role(body.role)
    with get_users_db() as conn:
        clash = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if clash is not None:
            raise HTTPException(
                status_code=409, detail="Cet identifiant est déjà utilisé"
            )
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, actif, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                username,
                seed.hash_password(body.password),
                display_name,
                role,
                1 if body.actif else 0,
                _now(),
            ),
        )
        row = conn.execute(USER_SELECT + " WHERE u.id = ?", (cur.lastrowid,)).fetchone()
    return _user_out(row)


@app.put("/api/users/{user_id}")
def update_user(
    user_id: int, body: UserPatch, user: dict = Depends(require_admin)
) -> dict:
    data = body.model_dump(exclude_unset=True)
    with get_users_db() as conn:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")

        display_name = existing["display_name"]
        if "display_name" in data:
            display_name = (data["display_name"] or "").strip()
            if not display_name:
                raise HTTPException(
                    status_code=400, detail="Le nom affiché est obligatoire"
                )

        role = existing["role"]
        if "role" in data:
            role = _require_role(data["role"])
            if user_id == user["id"] and role != ROLE_ADMIN:
                raise HTTPException(
                    status_code=400,
                    detail="Vous ne pouvez pas retirer votre propre rôle administrateur",
                )

        actif = existing["actif"]
        if "actif" in data:
            actif = 1 if data["actif"] else 0
            if not actif and user_id == user["id"]:
                raise HTTPException(
                    status_code=400,
                    detail="Vous ne pouvez pas désactiver votre propre compte",
                )

        password_hash = existing["password_hash"]
        if data.get("password"):
            if len(data["password"]) < 4:
                raise HTTPException(
                    status_code=400,
                    detail="Le mot de passe doit contenir au moins 4 caractères",
                )
            password_hash = seed.hash_password(data["password"])

        conn.execute(
            "UPDATE users SET display_name = ?, role = ?, actif = ?, password_hash = ? "
            "WHERE id = ?",
            (display_name, role, actif, password_hash, user_id),
        )
        if not actif:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        row = conn.execute(USER_SELECT + " WHERE u.id = ?", (user_id,)).fetchone()
    result = _user_out(row)
    result["dossier_count"] = _dossier_counts_by_user().get(user_id, 0)
    return result


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, user: dict = Depends(require_admin)) -> dict:
    if user_id == user["id"]:
        raise HTTPException(
            status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte"
        )
    with get_users_db() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    # Les dossiers et remarques sont dans l'autre base : on y vérifie les liens.
    with get_db() as conn:
        linked = conn.execute(
            "SELECT (SELECT COUNT(*) FROM dossiers "
            "        WHERE verifier_id = ? AND deleted_at IS NULL) "
            "     + (SELECT COUNT(*) FROM remarks WHERE author_id = ?) AS n",
            (user_id, user_id),
        ).fetchone()["n"]
    if linked:
        raise HTTPException(
            status_code=409,
            detail="Ce compte est lié à des dossiers ou des remarques : "
            "il ne peut pas être supprimé",
        )
    with get_users_db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}


@app.get("/api/checkpoints")
def list_checkpoints(
    type: str | None = None, user: dict = Depends(current_user)
) -> list[dict]:
    """Points de contrôle, filtrés par type quand ?type= est fourni."""
    with get_db() as conn:
        if type is not None:
            _require_type(type)
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE applicable_dossier_type = ? "
                "ORDER BY is_mandatory DESC, name",
                (type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM checkpoints "
                "ORDER BY applicable_dossier_type, is_mandatory DESC, name"
            ).fetchall()
    return [_checkpoint_out(r) for r in rows]


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------


class DossierIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    type: str
    created_date: str | None = None
    parent_dossier_id: int | None = None
    observation: str | None = Field(default=None, max_length=5000)
    # État « Reçu » et statut « En cours » par défaut, tous deux modifiables.
    state: str = DEFAULT_STATE
    status: str = DEFAULT_STATUS


class DossierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    state: str | None = None
    status: str | None = None
    created_date: str | None = None
    parent_dossier_id: int | None = None
    observation: str | None = Field(default=None, max_length=5000)


@app.get("/api/dossiers")
def list_dossiers(
    type: str | None = None,
    state: str | None = None,
    status: str | None = None,
    verifier_id: int | None = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    clauses: list[str] = ["d.deleted_at IS NULL"]
    params: list = []
    if type is not None:
        clauses.append("d.type = ?")
        params.append(_require_type(type))
    if state is not None:
        clauses.append("d.state = ?")
        params.append(_require_state(state))
    if status is not None:
        clauses.append("d.status = ?")
        params.append(_require_status(status))
    if verifier_id is not None:
        clauses.append("d.verifier_id = ?")
        params.append(verifier_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db() as conn:
        rows = conn.execute(
            DOSSIER_SELECT + where + " ORDER BY d.id DESC", params
        ).fetchall()
    return _dossiers_out(rows)


@app.post("/api/dossiers", status_code=201)
def create_dossier(body: DossierIn, user: dict = Depends(require_write)) -> dict:
    """Crée un dossier.

    Le numéro de référence est attribué à partir du compteur persistant de son
    type, la date est celle du jour (sauf si une date est fournie) et le
    vérificateur vient de l'utilisateur connecté : le corps de la requête est
    volontairement ignoré pour ce dernier.
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom est obligatoire")
    dossier_type = _require_type(body.type)
    # État et statut initiaux, modifiables dès la création.
    state = _require_state(body.state)
    status = _require_status(body.status)
    created_date = _parse_date(body.created_date) if body.created_date else _today()
    observation = (body.observation or "").strip() or None
    now = _now()

    with get_db() as conn:
        parent_id = _resolve_parent(conn, body.parent_dossier_id, dossier_id=None)
        # Une seule transaction : attribuer le numéro et insérer la ligne
        # ensemble, pour que deux créations simultanées ne reçoivent jamais le
        # même numéro.
        conn.execute("BEGIN IMMEDIATE")
        try:
            reference = db.next_reference_number(conn, dossier_type)
            cur = conn.execute(
                "INSERT INTO dossiers (reference_number, name, type, state, status, "
                "created_date, withdrawal_date, withdrawn_by, observation, verifier_id, "
                "parent_dossier_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reference,
                    name,
                    dossier_type,
                    state,
                    status,
                    created_date,
                    _today() if state == "Retiré" else None,
                    None,
                    observation,
                    user["id"],
                    parent_id,
                    now,
                    now,
                ),
            )
            dossier_id = cur.lastrowid
            conn.execute("COMMIT")
        except db.NumberingRangeExhausted as exc:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception:
            conn.execute("ROLLBACK")
            raise
        row = conn.execute(DOSSIER_SELECT + " WHERE d.id = ?", (dossier_id,)).fetchone()
    return _dossier_single_out(row)


@app.get("/api/dossiers/{dossier_id}")
def get_dossier(dossier_id: int, user: dict = Depends(current_user)) -> dict:
    with get_db() as conn:
        row = conn.execute(
            DOSSIER_SELECT + " WHERE d.id = ? AND d.deleted_at IS NULL", (dossier_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        checkpoints = conn.execute(
            "SELECT * FROM checkpoints WHERE applicable_dossier_type = ? "
            "ORDER BY is_mandatory DESC, name",
            (row["type"],),
        ).fetchall()
    out = _dossier_single_out(row)
    out["checkpoints"] = [_checkpoint_out(c) for c in checkpoints]
    return out


@app.put("/api/dossiers/{dossier_id}")
def update_dossier(
    dossier_id: int, body: DossierPatch, user: dict = Depends(require_write)
) -> dict:
    data = body.model_dump(exclude_unset=True)
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM dossiers WHERE id = ? AND deleted_at IS NULL", (dossier_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        name = existing["name"]
        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="Le nom est obligatoire")

        state = existing["state"]
        if "state" in data:
            state = _require_state(data["state"])

        status = existing["status"]
        if "status" in data:
            status = _require_status(data["status"])
        elif state == "Retiré" and status == "En cours":
            # Retirer un dossier jamais visé le fait passer au statut « Retour ».
            status = "Retour"

        created_date = existing["created_date"]
        if "created_date" in data and data["created_date"]:
            created_date = _parse_date(data["created_date"])

        parent_id = existing["parent_dossier_id"]
        if "parent_dossier_id" in data:
            parent_id = _resolve_parent(conn, data["parent_dossier_id"], dossier_id)

        observation = existing["observation"]
        if "observation" in data:
            observation = (data["observation"] or "").strip() or None

        # La date de retrait (et le nom de celui qui retire) suivent l'état :
        # renseignés au passage à « Retiré », effacés au retour à « Reçu ».
        withdrawal_date = existing["withdrawal_date"]
        withdrawn_by = existing["withdrawn_by"]
        if state == "Retiré":
            withdrawal_date = withdrawal_date or _today()
        else:
            withdrawal_date = None
            withdrawn_by = None

        conn.execute(
            "UPDATE dossiers SET name = ?, state = ?, status = ?, created_date = ?, "
            "parent_dossier_id = ?, withdrawal_date = ?, withdrawn_by = ?, "
            "observation = ?, updated_at = ? WHERE id = ?",
            (
                name,
                state,
                status,
                created_date,
                parent_id,
                withdrawal_date,
                withdrawn_by,
                observation,
                _now(),
                dossier_id,
            ),
        )
        row = conn.execute(
            DOSSIER_SELECT + " WHERE d.id = ?", (dossier_id,)
        ).fetchone()
    return _dossier_single_out(row)


class WithdrawIn(BaseModel):
    withdrawn_by: str = Field(min_length=1, max_length=200)
    remark: str | None = Field(default=None, max_length=5000)


class ReceiveIn(BaseModel):
    remark: str | None = Field(default=None, max_length=5000)


class StatusChangeIn(BaseModel):
    status: str
    remark: str | None = Field(default=None, max_length=5000)


def _add_remark_text(conn, dossier_id: int, text: str | None, author_id: int) -> None:
    """Ajoute une remarque si un texte non vide est fourni."""
    text = (text or "").strip()
    if not text:
        return
    conn.execute(
        "INSERT INTO remarks (dossier_id, comment_text, author_id, date) "
        "VALUES (?, ?, ?, ?)",
        (dossier_id, text, author_id, _now()),
    )


def _existing_dossier(conn, dossier_id: int):
    row = conn.execute(
        "SELECT * FROM dossiers WHERE id = ? AND deleted_at IS NULL", (dossier_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return row


@app.post("/api/dossiers/{dossier_id}/withdraw")
def withdraw_dossier(
    dossier_id: int, body: WithdrawIn, user: dict = Depends(require_write)
) -> dict:
    """Passe le dossier à l'état « Retiré » en enregistrant qui l'a retiré."""
    withdrawn_by = body.withdrawn_by.strip()
    if not withdrawn_by:
        raise HTTPException(
            status_code=400, detail="Le nom de la personne qui retire est obligatoire"
        )
    with get_db() as conn:
        _existing_dossier(conn, dossier_id)
        now = _now()
        # Un dossier encore « En cours » qui est retiré n'a jamais été visé :
        # son statut devient « Retour ».  Un statut déjà tranché est conservé.
        conn.execute(
            "UPDATE dossiers SET state = 'Retiré', "
            "status = CASE WHEN status = 'En cours' THEN 'Retour' ELSE status END, "
            "withdrawal_date = ?, withdrawn_by = ?, updated_at = ? WHERE id = ?",
            (_today(), withdrawn_by, now, dossier_id),
        )
        _add_remark_text(conn, dossier_id, body.remark, user["id"])
        row = conn.execute(DOSSIER_SELECT + " WHERE d.id = ?", (dossier_id,)).fetchone()
    return _dossier_single_out(row)


@app.post("/api/dossiers/{dossier_id}/receive")
def receive_dossier(
    dossier_id: int, body: ReceiveIn, user: dict = Depends(require_write)
) -> dict:
    """Remet le dossier à l'état « Reçu » et efface la date de retrait."""
    with get_db() as conn:
        _existing_dossier(conn, dossier_id)
        conn.execute(
            "UPDATE dossiers SET state = 'Reçu', withdrawal_date = NULL, "
            "withdrawn_by = NULL, updated_at = ? WHERE id = ?",
            (_now(), dossier_id),
        )
        _add_remark_text(conn, dossier_id, body.remark, user["id"])
        row = conn.execute(DOSSIER_SELECT + " WHERE d.id = ?", (dossier_id,)).fetchone()
    return _dossier_single_out(row)


@app.post("/api/dossiers/{dossier_id}/status")
def change_dossier_status(
    dossier_id: int, body: StatusChangeIn, user: dict = Depends(require_write)
) -> dict:
    """Change le statut (En cours / Visé / Rejeté) avec remarque facultative."""
    status = _require_status(body.status)
    with get_db() as conn:
        _existing_dossier(conn, dossier_id)
        conn.execute(
            "UPDATE dossiers SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), dossier_id),
        )
        _add_remark_text(conn, dossier_id, body.remark, user["id"])
        row = conn.execute(DOSSIER_SELECT + " WHERE d.id = ?", (dossier_id,)).fetchone()
    return _dossier_single_out(row)


@app.delete("/api/dossiers/{dossier_id}")
def delete_dossier(dossier_id: int, user: dict = Depends(require_write)) -> dict:
    """Suppression logique : la ligne reste en base, horodatée par deleted_at."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM dossiers WHERE id = ? AND deleted_at IS NULL", (dossier_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        now = _now()
        conn.execute(
            "UPDATE dossiers SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, dossier_id),
        )
    return {"ok": True, "id": dossier_id, "deleted_at": now}


# ---------------------------------------------------------------------------
# Remarques
# ---------------------------------------------------------------------------


class RemarkIn(BaseModel):
    comment_text: str = Field(min_length=1, max_length=5000)


@app.get("/api/dossiers/{dossier_id}/remarks")
def list_remarks(dossier_id: int, user: dict = Depends(current_user)) -> list[dict]:
    with get_db() as conn:
        if conn.execute(
            "SELECT 1 FROM dossiers WHERE id = ? AND deleted_at IS NULL", (dossier_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        rows = conn.execute(
            "SELECT r.* FROM remarks r "
            "WHERE r.dossier_id = ? ORDER BY r.date DESC, r.id DESC",
            (dossier_id,),
        ).fetchall()
    noms = _user_names({row["author_id"] for row in rows})
    return [_remark_out(row, noms.get(row["author_id"], "—")) for row in rows]


@app.post("/api/dossiers/{dossier_id}/remarks", status_code=201)
def add_remark(
    dossier_id: int, body: RemarkIn, user: dict = Depends(require_write)
) -> dict:
    text = body.comment_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Le texte de la remarque est obligatoire")
    with get_db() as conn:
        if conn.execute(
            "SELECT 1 FROM dossiers WHERE id = ? AND deleted_at IS NULL", (dossier_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        # L'auteur vient de la session, jamais du client.
        cur = conn.execute(
            "INSERT INTO remarks (dossier_id, comment_text, author_id, date) "
            "VALUES (?, ?, ?, ?)",
            (dossier_id, text, user["id"], _now()),
        )
        remark_id = cur.lastrowid
        row = conn.execute(
            "SELECT r.* FROM remarks WHERE r.id = ?", (remark_id,)
        ).fetchone()
    return _remark_out(
        row, _user_names({row["author_id"]}).get(row["author_id"], "—")
    )


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)) -> dict:
    with get_db() as conn:
        count_rows = conn.execute(
            "SELECT type, status, COUNT(*) AS count FROM dossiers "
            "WHERE deleted_at IS NULL GROUP BY type, status"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM dossiers WHERE deleted_at IS NULL"
        ).fetchone()["n"]
        recent_remarks = conn.execute(
            "SELECT r.id, r.comment_text, r.date, r.dossier_id, r.author_id, "
            "d.reference_number "
            "FROM remarks r "
            "JOIN dossiers d ON d.id = r.dossier_id "
            "WHERE d.deleted_at IS NULL "
            "ORDER BY r.date DESC, r.id DESC LIMIT 8"
        ).fetchall()
        recent_dossiers = conn.execute(
            "SELECT d.id, d.reference_number, d.name, d.type, d.state, d.status, "
            "d.created_date, d.withdrawal_date, d.withdrawn_by, d.verifier_id "
            "FROM dossiers d "
            "WHERE d.deleted_at IS NULL "
            "ORDER BY d.id DESC LIMIT 8"
        ).fetchall()

    # Noms des comptes concernés, lus dans la base des utilisateurs.
    noms = _user_names(
        {row["verifier_id"] for row in recent_dossiers}
        | {row["author_id"] for row in recent_remarks}
    )

    matrix = {t: {s: 0 for s in DOSSIER_STATUSES} for t in DOSSIER_TYPES}
    for row in count_rows:
        matrix[row["type"]][row["status"]] = row["count"]

    counts = [
        {"type": t, "counts": matrix[t], "total": sum(matrix[t].values())}
        for t in DOSSIER_TYPES
    ]
    by_status = {s: sum(matrix[t][s] for t in DOSSIER_TYPES) for s in DOSSIER_STATUSES}

    activity: list[dict] = []
    for row in recent_dossiers:
        activity.append(
            {
                "kind": "created",
                "at": row["created_date"],
                "dossier_id": row["id"],
                "reference_number": row["reference_number"],
                "name": row["name"],
                "text": row["name"],
                "who": noms.get(row["verifier_id"], "—"),
            }
        )
        if row["withdrawal_date"]:
            activity.append(
                {
                    "kind": "withdrawn",
                    "at": row["withdrawal_date"],
                    "dossier_id": row["id"],
                    "reference_number": row["reference_number"],
                    "name": row["name"],
                    "text": row["name"],
                    "who": row["withdrawn_by"] or "—",
                }
            )
    for row in recent_remarks:
        activity.append(
            {
                "kind": "remark",
                "at": row["date"],
                "dossier_id": row["dossier_id"],
                "reference_number": row["reference_number"],
                "name": "",
                "text": row["comment_text"],
                "who": noms.get(row["author_id"], "—"),
            }
        )
    activity.sort(key=lambda item: item["at"], reverse=True)

    return {
        "total": total,
        "counts": counts,
        "by_status": by_status,
        "activity": activity[:15],
    }


# ---------------------------------------------------------------------------
# Base de données : export, import, réinitialisation
# ---------------------------------------------------------------------------

#: Taille maximale acceptée pour un fichier de base importé (512 Mo).
IMPORT_MAX_BYTES = 512 * 1024 * 1024

#: Tables qu'un fichier importé doit contenir pour être exploitable ici.
REQUIRED_TABLES = ("dossiers", "checkpoints", "counters", "remarks")


def _data_directory() -> str:
    """Dossier de la base, créé au besoin (fichiers temporaires d'échange)."""
    dossier = os.path.dirname(db.DB_PATH) or "."
    os.makedirs(dossier, exist_ok=True)
    return dossier


def _replace_database(source: str) -> None:
    """Remplace atomiquement la base courante par le fichier ``source``.

    Les connexions sont ouvertes le temps d'une requête (voir get_db) : aucun
    fichier n'est donc maintenu ouvert entre deux appels.  Les fichiers annexes
    SQLite (-journal, -wal, -shm) de l'ancienne base sont supprimés pour qu'ils
    ne soient jamais rejoués sur la nouvelle.
    """
    for suffixe in ("-journal", "-wal", "-shm"):
        annexe = db.DB_PATH + suffixe
        if os.path.exists(annexe):
            os.remove(annexe)
    os.replace(source, db.DB_PATH)


def _database_counts() -> dict:
    with get_users_db() as uconn:
        users = uconn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    with get_db() as conn:
        return {
            "users": users,
            "dossiers": conn.execute(
                "SELECT COUNT(*) AS n FROM dossiers WHERE deleted_at IS NULL"
            ).fetchone()["n"],
            "remarks": conn.execute("SELECT COUNT(*) AS n FROM remarks").fetchone()["n"],
            "checkpoints": conn.execute(
                "SELECT COUNT(*) AS n FROM checkpoints"
            ).fetchone()["n"],
        }


def _snapshot_database() -> bytes:
    """Copie cohérente de la base via l'API de sauvegarde SQLite.

    L'instantané est pris par SQLite lui-même : il reste valide même si une
    écriture a lieu au même moment, contrairement à une simple copie du fichier.
    """
    dossier = _data_directory()
    descripteur, chemin = tempfile.mkstemp(
        prefix="dossiers-export-", suffix=".db", dir=dossier
    )
    os.close(descripteur)
    try:
        with get_db() as conn:
            destination = sqlite3.connect(chemin)
            try:
                conn.backup(destination)
            finally:
                destination.close()
        with open(chemin, "rb") as fichier:
            return fichier.read()
    finally:
        if os.path.exists(chemin):
            os.unlink(chemin)


def _validate_database_file(chemin: str) -> None:
    """Refuse un fichier qui n'est pas une base exploitable par l'application."""
    try:
        conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    except sqlite3.Error:
        raise HTTPException(
            status_code=400, detail="Fichier illisible : ce n'est pas une base SQLite."
        )
    try:
        try:
            verif = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError:
            raise HTTPException(
                status_code=400, detail="Fichier invalide : ce n'est pas une base SQLite."
            )
        if verif is None or verif[0] != "ok":
            raise HTTPException(
                status_code=400,
                detail="Base corrompue : la vérification d'intégrité a échoué.",
            )
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        manquantes = [t for t in REQUIRED_TABLES if t not in tables]
        if manquantes:
            raise HTTPException(
                status_code=400,
                detail="Ce fichier n'est pas une base de « Suivi des dossiers » "
                "(tables manquantes : " + ", ".join(manquantes) + ").",
            )
    finally:
        conn.close()


@app.get("/api/database/info")
def database_info(user: dict = Depends(current_user)) -> dict:
    """Emplacement, taille et volumes des deux bases."""
    infos = _database_counts()
    for cle, chemin in (
        ("size_bytes", db.DB_PATH),
        ("users_size_bytes", db.USERS_DB_PATH),
    ):
        try:
            infos[cle] = os.path.getsize(chemin)
        except OSError:
            infos[cle] = 0
    infos["path"] = db.DB_PATH
    infos["users_path"] = db.USERS_DB_PATH
    return infos


@app.get("/api/database/export")
def export_database(user: dict = Depends(current_user)) -> Response:
    """Télécharge une copie complète de la base (.db)."""
    contenu = _snapshot_database()
    nom = f"dossiers-{_today()}.db"
    return Response(
        content=contenu,
        media_type="application/vnd.sqlite3",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@app.post("/api/database/import")
async def import_database(
    request: Request, user: dict = Depends(require_write)
) -> dict:
    """Remplace la base courante par un fichier .db envoyé dans le corps.

    Le corps brut (application/octet-stream) est utilisé plutôt qu'un formulaire
    multipart : aucune dépendance supplémentaire n'est ainsi nécessaire.
    """
    contenu = await request.body()
    if not contenu:
        raise HTTPException(status_code=400, detail="Aucun fichier reçu.")
    if len(contenu) > IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=413, detail="Fichier trop volumineux (512 Mo maximum)."
        )
    if not contenu.startswith(b"SQLite format 3\x00"):
        raise HTTPException(
            status_code=400,
            detail="Fichier invalide : ce n'est pas une base SQLite (.db).",
        )

    dossier = _data_directory()
    descripteur, chemin = tempfile.mkstemp(
        prefix="dossiers-import-", suffix=".db", dir=dossier
    )
    try:
        with os.fdopen(descripteur, "wb") as fichier:
            fichier.write(contenu)
        _validate_database_file(chemin)
        # La base des comptes n'est jamais remplacée : un ancien export qui en
        # contient encore se voit retirer ces tables avant d'être installé.
        db.sanitize_dossiers_file(chemin)
        _replace_database(chemin)
    except Exception:
        if os.path.exists(chemin):
            os.unlink(chemin)
        raise

    # Base de dossiers mise à niveau et points de contrôle garantis ; les
    # comptes et les sessions ne bougent pas.
    db.init_db()
    seed.run()

    resultat = _database_counts()
    resultat.update({"ok": True, "reconnect": False})
    return resultat


@app.post("/api/database/reset")
def reset_database(user: dict = Depends(require_admin)) -> dict:
    """Remet la base des dossiers à zéro ; les comptes sont conservés."""
    dossier = _data_directory()
    descripteur, chemin = tempfile.mkstemp(
        prefix="dossiers-reinit-", suffix=".db", dir=dossier
    )
    os.close(descripteur)
    try:
        # Une base neuve est construite à côté puis mise en place d'un seul coup :
        # aucune fenêtre pendant laquelle la base serait absente ou incomplète.
        conn = sqlite3.connect(chemin, isolation_level=None)
        try:
            conn.executescript(db.DOSSIERS_SCHEMA)
            for dossier_type, rule in NUMBERING_RULES.items():
                conn.execute(
                    "INSERT OR IGNORE INTO counters (type, last_number) VALUES (?, ?)",
                    (dossier_type, int(rule["start"]) - 1),
                )
        finally:
            conn.close()
        _replace_database(chemin)
    except Exception:
        if os.path.exists(chemin):
            os.unlink(chemin)
        raise

    seed.run()  # catalogue des points de contrôle (les comptes ne changent pas)

    resultat = _database_counts()
    resultat.update({"ok": True, "reconnect": False})
    return resultat


# ---------------------------------------------------------------------------
# Mise à jour de l'application (Git, depuis l'interface)
# ---------------------------------------------------------------------------
#
# Ces routes remplacent le « git pull » en ligne de commande : elles sont
# réservées à l'administrateur et n'agissent que sur le dossier de
# l'application (BASE_DIR).  Aucun chemin ne vient du client : le dépôt, la
# branche et la branche distante sont déterminés par Git lui-même.

#: Durée maximale d'une opération Git (réseau compris).
GIT_TIMEOUT = 180

#: Laisse le temps à la réponse HTTP de partir avant de remplacer le processus.
DELAI_REDEMARRAGE = 1.5

# Adresse réellement utilisée au démarrage, reprise telle quelle au redémarrage.
_host_effectif: str | None = None
_port_effectif: int | None = None

_redemarrage_verrou = threading.Lock()
_redemarrage_planifie = False


def _git(*arguments: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Exécute Git dans le dossier de l'application, sans interaction possible."""
    environnement = os.environ.copy()
    environnement.update(
        {
            # Une demande d'identifiant ou de mot de passe ferait attendre la
            # requête jusqu'au délai maximum : on échoue franchement à la place.
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "GIT_SSH_COMMAND": environnement.get(
                "GIT_SSH_COMMAND", "ssh -o BatchMode=yes"
            ),
            "LC_ALL": "C",
        }
    )
    return subprocess.run(
        ["git", "-C", BASE_DIR, *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environnement,
        cwd=BASE_DIR,
    )


def _git_lancer(*arguments: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Comme _git(), mais traduit les échecs système en erreurs HTTP."""
    try:
        return _git(*arguments, timeout=timeout)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400, detail="Git n'est pas installé sur cette machine."
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="Opération Git interrompue : délai dépassé (réseau ou dépôt "
            "distant indisponible).",
        )


def _git_sortie(resultat: subprocess.CompletedProcess) -> str:
    """Sortie de Git (stdout puis stderr), utilisable telle quelle dans un message."""
    return ((resultat.stdout or "") + (resultat.stderr or "")).strip()


def _git_commit(revision: str = "HEAD") -> dict | None:
    """Commit d'une révision : identifiant, forme courte, sujet et date."""
    resultat = _git("log", "-1", "--format=%H%x00%h%x00%s%x00%cI", revision)
    if resultat.returncode != 0 or not resultat.stdout.strip():
        return None
    morceaux = (resultat.stdout.rstrip("\n").split("\x00") + ["", "", "", ""])[:4]
    return {
        "hash": morceaux[0],
        "short": morceaux[1],
        "subject": morceaux[2],
        "date": morceaux[3],
    }


def _git_fichiers_modifies() -> list[str]:
    """Fichiers suivis par Git et modifiés localement (hors fichiers ignorés)."""
    resultat = _git("status", "--porcelain", "--untracked-files=no")
    if resultat.returncode != 0:
        return []
    fichiers = []
    for ligne in resultat.stdout.splitlines():
        nom = ligne[3:].strip()
        if " -> " in nom:  # renommage : seul le nouveau nom compte
            nom = nom.split(" -> ", 1)[1]
        if nom:
            fichiers.append(nom)
    return fichiers


def _git_ecart(suivi: str) -> tuple[int, int]:
    """(commits en avance, commits en retard) par rapport à la branche distante."""
    resultat = _git("rev-list", "--left-right", "--count", f"HEAD...{suivi}")
    if resultat.returncode != 0:
        return 0, 0
    morceaux = resultat.stdout.split()
    if len(morceaux) != 2:
        return 0, 0
    try:
        return int(morceaux[0]), int(morceaux[1])
    except ValueError:
        return 0, 0


def _git_commits_entrants(suivi: str, limite: int = 15) -> list[dict]:
    """Commits présents sur la branche distante mais pas encore installés."""
    resultat = _git(
        "log", f"--max-count={int(limite)}", "--format=%h%x00%s%x00%cI", f"HEAD..{suivi}"
    )
    if resultat.returncode != 0:
        return []
    commits = []
    for ligne in resultat.stdout.splitlines():
        morceaux = (ligne.split("\x00") + ["", "", ""])[:3]
        if morceaux[0]:
            commits.append(
                {"short": morceaux[0], "subject": morceaux[1], "date": morceaux[2]}
            )
    return commits


def _etat_mise_a_jour() -> dict:
    """Décrit l'installation locale : dépôt, branche et commit installés.

    Aucun accès réseau : la vérification des nouveautés est une action séparée.
    """
    etat: dict = {
        "supported": False,
        "reason": "",
        "version": app.version,
        "branch": None,
        "upstream": None,
        "remote": None,
        "commit": None,
        "dirty": False,
        "dirty_files": [],
        "checked": False,
        "ahead": 0,
        "behind": 0,
        "update_available": False,
        "commits": [],
        "can_restart": not getattr(sys, "frozen", False),
        "restart_pending": _redemarrage_planifie,
    }

    if getattr(sys, "frozen", False):
        etat["reason"] = (
            "Cette installation est un exécutable autonome : la mise à jour se "
            "fait en remplaçant le fichier de l'application."
        )
        return etat
    if shutil.which("git") is None:
        etat["reason"] = "Git n'est pas installé sur cette machine."
        return etat
    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        etat["reason"] = (
            "Cette installation n'est pas un dépôt Git (copie manuelle ou add-on "
            "Home Assistant) : réinstallez l'application pour la mettre à jour."
        )
        return etat
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        etat["reason"] = "Le dossier de l'application n'est pas un dépôt Git exploitable."
        return etat

    branche = _git("rev-parse", "--abbrev-ref", "HEAD")
    suivi = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    remote = _git("remote", "get-url", "origin")

    etat["branch"] = branche.stdout.strip() if branche.returncode == 0 else None
    etat["upstream"] = suivi.stdout.strip() if suivi.returncode == 0 else None
    etat["remote"] = remote.stdout.strip() if remote.returncode == 0 else None
    etat["commit"] = _git_commit()
    etat["dirty_files"] = _git_fichiers_modifies()
    etat["dirty"] = bool(etat["dirty_files"])

    if not etat["upstream"]:
        etat["reason"] = (
            "La branche « " + str(etat["branch"] or "courante") + " » ne suit aucune "
            "branche distante : associez-la une fois avec "
            "git branch --set-upstream-to=origin/" + str(etat["branch"] or "main") + "."
        )
        return etat

    etat["supported"] = True
    return etat


@app.get("/api/update/info")
def update_info(user: dict = Depends(current_user)) -> dict:
    """Version installée, dépôt, branche et commit (sans accès réseau)."""
    return _etat_mise_a_jour()


@app.post("/api/update/check")
def update_check(user: dict = Depends(require_admin)) -> dict:
    """Interroge le dépôt distant et indique les commits non installés."""
    etat = _etat_mise_a_jour()
    if not etat["supported"]:
        raise HTTPException(status_code=400, detail=etat["reason"])

    recuperation = _git_lancer("fetch", "--prune", "origin")
    if recuperation.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail="Récupération impossible : "
            + (_git_sortie(recuperation) or "le dépôt distant n'a pas répondu."),
        )

    suivi = etat["upstream"]
    en_avance, en_retard = _git_ecart(suivi)
    etat.update(
        {
            "checked": True,
            "ahead": en_avance,
            "behind": en_retard,
            "update_available": en_retard > 0,
            "commits": _git_commits_entrants(suivi) if en_retard > 0 else [],
            "commit": _git_commit(),
        }
    )
    return etat


@app.post("/api/update/apply")
def update_apply(user: dict = Depends(require_admin)) -> dict:
    """Installe les nouveautés : « git pull --ff-only » dans le dossier de l'app.

    La mise à jour est volontairement limitée à une avance rapide : aucune fusion
    ni commit n'est créé sur la machine, et un conflit échoue sans rien écraser.
    """
    etat = _etat_mise_a_jour()
    if not etat["supported"]:
        raise HTTPException(status_code=400, detail=etat["reason"])

    avant = etat["commit"]
    resultat = _git_lancer("pull", "--ff-only")
    if resultat.returncode != 0:
        raise HTTPException(
            status_code=409,
            detail="Mise à jour impossible : "
            + (_git_sortie(resultat) or "Git a refusé l'opération."),
        )

    apres = _git_commit() or avant
    installe = bool(avant and apres and avant["hash"] != apres["hash"])
    fichiers: list[str] = []
    if installe and avant:
        diff = _git("diff", "--name-only", f"{avant['hash']}..{apres['hash']}")
        fichiers = [ligne.strip() for ligne in diff.stdout.splitlines() if ligne.strip()]

    # Les dépendances ne s'installent pas seules : on le signale pour que le
    # lanceur soit relancé avec --reinstall.
    dependances = [
        f
        for f in fichiers
        if os.path.basename(f).startswith("requirements") and f.endswith(".txt")
    ]

    return {
        "ok": True,
        "updated": installe,
        "before": avant,
        "after": apres,
        "files": fichiers,
        "deps_changed": bool(dependances),
        "deps_files": dependances,
        "restart_required": installe,
        "can_restart": not getattr(sys, "frozen", False),
        "branch": etat["branch"],
        "upstream": etat["upstream"],
        "output": _git_sortie(resultat),
    }


def _redemarrer_processus() -> None:
    """Remplace le processus courant par une application à jour (os.exec*).

    Le port se libère avec l'ancien processus et le nouveau code démarre sur la
    même adresse.  En cas d'échec, l'ancienne version continue de servir : rien
    n'est interrompu.
    """
    global _redemarrage_planifie

    environnement = os.environ.copy()
    if _host_effectif:
        environnement["HOST"] = str(_host_effectif)
    if _port_effectif:
        environnement["PORT"] = str(_port_effectif)

    try:
        os.chdir(BASE_DIR)
        os.execve(
            sys.executable,
            [sys.executable, os.path.join(BASE_DIR, "main.py")],
            environnement,
        )
    except Exception as erreur:  # noqa: BLE001 - le serveur actuel doit rester en vie
        print(f"[mise à jour] redémarrage impossible : {erreur}", flush=True)
        with _redemarrage_verrou:
            _redemarrage_planifie = False


@app.post("/api/update/restart")
def update_restart(user: dict = Depends(require_admin)) -> dict:
    """Redémarre l'application pour charger le code fraîchement récupéré."""
    global _redemarrage_planifie

    if getattr(sys, "frozen", False):
        raise HTTPException(
            status_code=400,
            detail="Un exécutable autonome se redémarre en le fermant puis en le "
            "relançant.",
        )
    with _redemarrage_verrou:
        if _redemarrage_planifie:
            return {"ok": True, "scheduled": True}
        _redemarrage_planifie = True

    minuteur = threading.Timer(DELAI_REDEMARRAGE, _redemarrer_processus)
    minuteur.daemon = True
    minuteur.start()
    return {"ok": True, "scheduled": True, "delay": DELAI_REDEMARRAGE}


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def _env_port() -> int:
    """Variable PORT, avec repli sur 8000 si absente, vide, nulle ou invalide."""
    try:
        port = int(os.environ.get("PORT") or 8000)
    except ValueError:
        return 8000
    return port if port > 0 else 8000


def main() -> None:
    import uvicorn

    global _host_effectif, _port_effectif

    host = os.environ.get("HOST") or "0.0.0.0"
    port = _env_port()
    # Retenus pour redémarrer sur la même adresse depuis l'interface.
    _host_effectif, _port_effectif = host, port
    print("=" * 60, flush=True)
    print("  Suivi des dossiers", flush=True)
    print(f"  Ouvrir http://{host}:{port} dans le navigateur", flush=True)
    print(f"  Base des dossiers     : {db.DB_PATH}", flush=True)
    print(f"  Base des utilisateurs : {db.USERS_DB_PATH}", flush=True)
    print("  Connexion de démonstration : admin / admin", flush=True)
    print("=" * 60, flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
