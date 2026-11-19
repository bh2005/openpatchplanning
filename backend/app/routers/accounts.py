"""Anmeldung, Benutzerverwaltung, API-Zugänge und Audit-Log."""
from __future__ import annotations

import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Security

from .. import audit, auth, db
from ..auth import Principal, current_principal, require_admin, require_user, session_header
from ..schemas import ChangePassword, LoginRequest, PasswordReset, TokenCreate, UserCreate, UserUpdate
from ..security import hash_password, new_api_token, token_hash, verify_password

router = APIRouter(tags=["konten"])

_NAME_RE = re.compile(r"^[A-Za-z0-9._\-@]{1,64}$")


# ── Anmeldung ─────────────────────────────────────────────────────────────────

@router.post("/auth/login")
def auth_login(body: LoginRequest):
    return auth.login(body.username, body.password)


@router.post("/auth/logout")
def auth_logout(token: Optional[str] = Security(session_header), _: Principal = Depends(require_user)):
    if token:
        auth.logout(token)
    return {"ok": True}


@router.get("/auth/me")
def auth_me(p: Principal = Depends(current_principal)):
    if p.kind == "token":
        return {"kind": "token", "name": p.name, "scope": p.scope}
    u = db.row("SELECT * FROM users WHERE id = ?", (p.user_id,))
    return {"kind": "user", **auth.public_user(u)}


@router.post("/auth/change-password")
def change_password(body: ChangePassword, p: Principal = Depends(require_user)):
    u = db.row("SELECT * FROM users WHERE id = ?", (p.user_id,))
    if u["source"] != "local":
        raise HTTPException(400, "Das Passwort dieses Kontos wird im Verzeichnisdienst geändert")
    if not verify_password(body.current_password, u["password_hash"]):
        raise HTTPException(401, "Aktuelles Passwort falsch")
    auth.check_password_policy(body.new_password)
    db.execute("UPDATE users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
               (hash_password(body.new_password), u["id"]))
    for t in [t for t, s in auth._sessions.items() if s["uid"] == u["id"]]:
        auth._sessions.pop(t, None)
    audit.log(p.name, "auth.password_change", "user", u["id"])
    return {"ok": True, "token": auth.new_session(u["id"])}       # alle anderen Sitzungen sind beendet, diese bleibt gültig


# ── Benutzerverwaltung (Admin) ────────────────────────────────────────────────

def _get_user(uid: int) -> dict:
    u = db.row("SELECT * FROM users WHERE id = ?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return u


def _last_admin_guard(u: dict, new_roles: list[str], new_active: bool) -> None:
    """Der letzte aktive Administrator darf weder herabgestuft noch deaktiviert/gelöscht werden."""
    if "admin" in auth.parse_roles(u["roles"]) and u["active"] and ("admin" not in new_roles or not new_active):
        n = db.row("SELECT COUNT(*) AS n FROM users WHERE active = 1 AND id <> ? AND (',' || roles || ',') LIKE '%,admin,%'", (u["id"],))["n"]
        if n == 0:
            raise HTTPException(400, "Der letzte aktive Administrator kann nicht geändert werden")


@router.get("/api/users")
def list_users(_: Principal = Depends(require_admin)):
    return [auth.public_user(u) for u in db.rows("SELECT * FROM users ORDER BY username COLLATE NOCASE")]


@router.post("/api/users", status_code=201)
def create_user(body: UserCreate, me: Principal = Depends(require_admin)):
    name = body.username.strip()
    if not _NAME_RE.match(name):
        raise HTTPException(400, "Benutzername: 1–64 Zeichen (Buchstaben, Ziffern, . _ - @)")
    roles = auth.check_roles(body.roles)
    auth.check_password_policy(body.password)
    try:
        uid = db.execute("INSERT INTO users(username, full_name, email, roles, source, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
                         (name, body.full_name.strip(), body.email.strip(), ",".join(roles), "local", hash_password(body.password), time.time()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Benutzername existiert bereits")
    audit.log(me.name, "user.create", "user", uid, f"{name} [{','.join(roles)}]")
    return auth.public_user(_get_user(uid))


@router.put("/api/users/{uid}")
def update_user(uid: int, body: UserUpdate, me: Principal = Depends(require_admin)):
    u = _get_user(uid)
    roles = auth.check_roles(body.roles) if body.roles is not None else auth.parse_roles(u["roles"])
    active = body.active if body.active is not None else bool(u["active"])
    _last_admin_guard(u, roles, active)
    db.execute("UPDATE users SET roles=?, active=?, full_name=?, email=? WHERE id=?",
               (",".join(roles), 1 if active else 0, body.full_name.strip() if body.full_name is not None else u["full_name"],
                body.email.strip() if body.email is not None else u["email"], uid))
    if not active or roles != auth.parse_roles(u["roles"]):
        auth.revoke_sessions(uid)                                # neue Rechte gelten sofort
    audit.log(me.name, "user.update", "user", uid, f"{u['username']} [{','.join(roles)}] aktiv={active}")
    return auth.public_user(_get_user(uid))


@router.post("/api/users/{uid}/reset-password")
def reset_password(uid: int, body: PasswordReset, me: Principal = Depends(require_admin)):
    u = _get_user(uid)
    if u["source"] != "local":
        raise HTTPException(400, "Verzeichnisdienst-Benutzer haben kein lokales Passwort")
    auth.check_password_policy(body.new_password)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), uid))
    auth.revoke_sessions(uid)
    audit.log(me.name, "user.password_reset", "user", uid, u["username"])
    return {"ok": True}


@router.post("/api/users/{uid}/revoke-sessions")
def revoke_user_sessions(uid: int, me: Principal = Depends(require_admin)):
    u = _get_user(uid)
    auth.revoke_sessions(uid)
    audit.log(me.name, "user.revoke_sessions", "user", uid, u["username"])
    return {"ok": True}


@router.delete("/api/users/{uid}")
def delete_user(uid: int, me: Principal = Depends(require_admin)):
    u = _get_user(uid)
    if u["id"] == me.user_id:
        raise HTTPException(400, "Das eigene Konto kann nicht gelöscht werden")
    _last_admin_guard(u, [], False)
    auth.revoke_sessions(uid)
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    audit.log(me.name, "user.delete", "user", uid, u["username"])
    return {"ok": True}


# ── API-Zugänge (Admin) ───────────────────────────────────────────────────────

def _token_out(t: dict) -> dict:
    return {k: t[k] for k in ("id", "name", "prefix", "scope", "created_by", "created_at", "expires_at", "last_used_at")} | {"revoked": bool(t["revoked"])}


@router.get("/api/tokens")
def list_tokens(_: Principal = Depends(require_admin)):
    return [_token_out(t) for t in db.rows("SELECT * FROM api_tokens ORDER BY id DESC")]


@router.post("/api/tokens", status_code=201)
def create_token(body: TokenCreate, me: Principal = Depends(require_admin)):
    if body.scope not in ("read", "write"):
        raise HTTPException(400, "Umfang muss 'read' oder 'write' sein")
    raw = new_api_token()
    now = time.time()
    tid = db.execute("INSERT INTO api_tokens(name, prefix, token_hash, scope, created_by, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                     (body.name.strip(), raw[:10], token_hash(raw), body.scope, me.name, now,
                      now + body.expires_days * 86400 if body.expires_days else None))
    audit.log(me.name, "token.create", "token", tid, f"{body.name} ({body.scope})")
    return {**_token_out(db.row("SELECT * FROM api_tokens WHERE id = ?", (tid,))), "token": raw,
            "hinweis": "Das Token wird nur jetzt angezeigt und kann nicht erneut abgerufen werden."}


@router.delete("/api/tokens/{tid}")
def revoke_token(tid: int, me: Principal = Depends(require_admin)):
    t = db.row("SELECT * FROM api_tokens WHERE id = ?", (tid,))
    if not t:
        raise HTTPException(404, "API-Zugang nicht gefunden")
    db.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (tid,))
    audit.log(me.name, "token.revoke", "token", tid, t["name"])
    return {"ok": True}


# ── Audit-Log ─────────────────────────────────────────────────────────────────

@router.get("/api/audit")
def get_audit(limit: int = 200, actor: str = "", entity: str = "", _: Principal = Depends(require_admin)):
    return audit.recent(limit, actor or None, entity or None)
