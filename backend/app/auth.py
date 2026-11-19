"""Anmeldung und Rechteprüfung.

Zwei Arten von Zugängen:
  * **Benutzer** (Web-UI): Anmeldung mit Benutzername/Passwort, Sitzungstoken im Header ``X-Auth-Token``.
    Sitzungen sind an ``users.token_version`` gebunden – Passwortwechsel, Rollenänderung und „Sitzungen beenden“ machen sie ungültig.
  * **API-Zugänge** (Skripte, Checkmk, OpenPlan): Token ``opp_…`` im Header ``Authorization: Bearer`` oder ``X-API-Key``;
    Umfang ``read`` (nur lesen) oder ``write`` (Stammdaten-Import/-Änderung). Ein API-Zugang kann nie Benutzer verwalten.

Rollen (kombinierbar): admin (alles), planer, freigeber, techniker, viewer.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from . import audit, db
from .config import settings
from .security import hash_password, new_session_token, token_hash, verify_password

ROLES = ("admin", "planer", "freigeber", "techniker", "viewer")

session_header = APIKeyHeader(name="X-Auth-Token", auto_error=False)
apikey_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_header = APIKeyHeader(name="Authorization", auto_error=False)

_sessions: dict[str, dict] = {}     # token -> {"uid": int, "tv": int, "exp": float}


@dataclass
class Principal:
    kind: str                         # "user" | "token"
    name: str
    roles: set = field(default_factory=set)
    scope: str = ""                   # nur Tokens: read | write
    user_id: Optional[int] = None

    def has(self, *roles: str) -> bool:
        return self.kind == "user" and ("admin" in self.roles or bool(self.roles & set(roles)))

    @property
    def is_admin(self) -> bool:
        return self.kind == "user" and "admin" in self.roles

    @property
    def can_write_master(self) -> bool:
        """Stammdaten (Standorte, Geräte, Ports, Import) ändern: Administratoren und API-Zugänge mit Umfang write."""
        return self.is_admin or (self.kind == "token" and self.scope == "write")


# ── Benutzer ──────────────────────────────────────────────────────────────────

def parse_roles(value: str) -> list[str]:
    return [r for r in (value or "").split(",") if r]


def public_user(u: dict) -> dict:
    return {
        "id": u["id"], "username": u["username"], "full_name": u["full_name"], "email": u["email"],
        "roles": parse_roles(u["roles"]), "source": u["source"], "active": bool(u["active"]),
        "created_at": u["created_at"], "last_login": u["last_login"],
    }


def check_password_policy(pw: str) -> None:
    if len(pw or "") < settings.min_password_len:
        raise HTTPException(400, f"Passwort muss mindestens {settings.min_password_len} Zeichen haben")


def check_roles(roles: list[str]) -> list[str]:
    bad = [r for r in roles if r not in ROLES]
    if bad:
        raise HTTPException(400, f"Unbekannte Rolle(n): {', '.join(bad)} (erlaubt: {', '.join(ROLES)})")
    if not roles:
        raise HTTPException(400, "Mindestens eine Rolle ist erforderlich")
    return sorted(set(roles), key=ROLES.index)


def init() -> Optional[str]:
    """Datenbank migrieren; legt den Start-Admin an, solange es noch keinen Benutzer gibt.

    Liefert das generierte Passwort zurück, wenn keines konfiguriert war (damit es einmalig geloggt werden kann)."""
    db.migrate()
    if db.row("SELECT COUNT(*) AS n FROM users")["n"] == 0:
        pw = settings.admin_password or secrets.token_urlsafe(12)
        db.execute(
            "INSERT INTO users(username, full_name, roles, source, password_hash, created_at) VALUES (?,?,?,?,?,?)",
            (settings.admin_username, "Administrator", "admin", "local", hash_password(pw), time.time()),
        )
        return None if settings.admin_password else pw
    return None


def login(username: str, password: str) -> dict:
    username = (username or "").strip()
    u = db.row("SELECT * FROM users WHERE username = ?", (username,)) if username else None
    if not u or u["source"] != "local" or not u["active"] or not verify_password(password or "", u["password_hash"]):
        audit.log(username or "?", "auth.login_failed")
        raise HTTPException(401, "Ungültige Anmeldedaten")
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), u["id"]))
    token = new_session_token()
    _sessions[token] = {"uid": u["id"], "tv": u["token_version"], "exp": time.time() + settings.session_ttl_hours * 3600}
    audit.log(u["username"], "auth.login")
    return {"token": token, "user": public_user(db.row("SELECT * FROM users WHERE id = ?", (u["id"],)))}


def logout(token: str) -> None:
    _sessions.pop(token, None)


def revoke_sessions(user_id: int) -> None:
    db.execute("UPDATE users SET token_version = token_version + 1 WHERE id = ?", (user_id,))
    for t in [t for t, s in _sessions.items() if s["uid"] == user_id]:
        _sessions.pop(t, None)


def new_session(user_id: int) -> str:
    u = db.row("SELECT * FROM users WHERE id = ?", (user_id,))
    token = new_session_token()
    _sessions[token] = {"uid": user_id, "tv": u["token_version"], "exp": time.time() + settings.session_ttl_hours * 3600}
    return token


# ── Auflösen des Aufrufers ────────────────────────────────────────────────────

def _principal_from_session(token: str) -> Principal:
    s = _sessions.get(token)
    if not s:
        raise HTTPException(401, "Ungültiger Token")
    if time.time() > s["exp"]:
        _sessions.pop(token, None)
        raise HTTPException(401, "Sitzung abgelaufen")
    u = db.row("SELECT * FROM users WHERE id = ?", (s["uid"],))
    if not u or not u["active"] or u["token_version"] != s["tv"]:
        _sessions.pop(token, None)
        raise HTTPException(401, "Sitzung nicht mehr gültig")
    return Principal("user", u["username"], set(parse_roles(u["roles"])), user_id=u["id"])


def _principal_from_api_token(raw: str) -> Principal:
    t = db.row("SELECT * FROM api_tokens WHERE token_hash = ?", (token_hash(raw),))
    now = time.time()
    if not t or t["revoked"] or (t["expires_at"] and t["expires_at"] < now):
        raise HTTPException(401, "Ungültiger oder abgelaufener API-Zugang")
    db.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now, t["id"]))
    return Principal("token", t["name"], set(), scope=t["scope"])


def current_principal(
    session: Optional[str] = Security(session_header),
    api_key: Optional[str] = Security(apikey_header),
    bearer: Optional[str] = Security(bearer_header),
) -> Principal:
    if session:
        return _principal_from_session(session)
    raw = api_key
    if not raw and bearer and bearer.lower().startswith("bearer "):
        raw = bearer[7:].strip()
    if raw:
        if raw.startswith("opp_"):
            return _principal_from_api_token(raw)
        raise HTTPException(401, "Ungültiger API-Zugang")
    raise HTTPException(401, "Nicht angemeldet")


def require_user(p: Principal = Depends(current_principal)) -> Principal:
    if p.kind != "user":
        raise HTTPException(403, "Nur für angemeldete Benutzer")
    return p


def require_admin(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_admin:
        raise HTTPException(403, "Nur für Administratoren")
    return p


def require_master_write(p: Principal = Depends(current_principal)) -> Principal:
    if not p.can_write_master:
        raise HTTPException(403, "Nur für Administratoren oder API-Zugänge mit Umfang „write“")
    return p


def require_roles(*roles: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.has(*roles):
            raise HTTPException(403, "Keine Berechtigung für diese Aktion")
        return p
    return dep
