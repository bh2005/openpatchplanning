"""Audit-Log: wer hat wann was geändert (Tabelle audit_log)."""
from __future__ import annotations

import time
from typing import Optional

from . import db


def log(actor: str, action: str, entity: str = "", entity_id: object = "", detail: str = "") -> None:
    db.execute(
        "INSERT INTO audit_log(ts, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
        (time.time(), actor or "?", action, entity, str(entity_id), detail[:2000]),
    )


def recent(limit: int = 200, actor: Optional[str] = None, entity: Optional[str] = None) -> list[dict]:
    where, args = [], []
    if actor:
        where.append("actor = ?"); args.append(actor)
    if entity:
        where.append("entity = ?"); args.append(entity)
    sql = "SELECT * FROM audit_log" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    return db.rows(sql, (*args, max(1, min(limit, 1000))))
