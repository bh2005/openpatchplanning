"""Katalog: frei pflegbare Kabelarten und Gerätemodelle (mit Port-Vorlagen)."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, db
from ..auth import Principal, current_principal, require_admin, require_master_write
from ..rackmount import check_mount
from ..schemas import CABLE_CATEGORIES, DEVICE_TYPES, PORT_MEDIA, CableTypeIn, DeviceModelIn

router = APIRouter(prefix="/api", tags=["katalog"])

MAX_TEMPLATE_PORTS = 1024


# ── Kabelarten ────────────────────────────────────────────────────────────────

def check_cable_type(name: str) -> str:
    """Prüft, dass eine aktive Kabelart mit diesem Namen existiert; liefert den gespeicherten Namen (Schreibweise des Katalogs)."""
    r = db.row("SELECT name, active FROM cable_types WHERE name = ?", (name,))
    if not r or not r["active"]:
        names = [x["name"] for x in db.rows("SELECT name FROM cable_types WHERE active = 1 ORDER BY sort, name")]
        raise HTTPException(400, f"Kabelart '{name}' ist ungültig (erlaubt: {', '.join(names)})")
    return r["name"]


def _cable_type_out(r: dict) -> dict:
    r = dict(r)
    r["builtin"] = bool(r["builtin"])
    r["active"] = bool(r["active"])
    r["in_use"] = (db.row("SELECT COUNT(*) AS n FROM cables WHERE cable_type = ?", (r["name"],))["n"]
                   + db.row("SELECT COUNT(*) AS n FROM workitems WHERE cable_type = ?", (r["name"],))["n"])
    return r


@router.get("/cable-types")
def list_cable_types(all: bool = False, _: Principal = Depends(current_principal)):
    where = "" if all else "WHERE active = 1"
    return [_cable_type_out(r) for r in db.rows(f"SELECT * FROM cable_types {where} ORDER BY sort, name COLLATE NOCASE")]


def _check_cable_type_body(body: CableTypeIn) -> None:
    if body.category not in CABLE_CATEGORIES:
        raise HTTPException(400, f"Kategorie '{body.category}' ist ungültig (erlaubt: {', '.join(CABLE_CATEGORIES)})")


@router.post("/cable-types", status_code=201)
def create_cable_type(body: CableTypeIn, me: Principal = Depends(require_admin)):
    _check_cable_type_body(body)
    try:
        cid = db.execute(
            "INSERT INTO cable_types(name, category, count_label, note, builtin, active, sort) VALUES (?,?,?,?,0,?,?)",
            (body.name.strip(), body.category, body.count_label.strip(), body.note.strip(), int(body.active), body.sort))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Die Kabelart '{body.name}' existiert bereits")
    audit.log(me.name, "cabletype.create", "cable_type", cid, body.name)
    return _cable_type_out(db.row("SELECT * FROM cable_types WHERE id = ?", (cid,)))


@router.put("/cable-types/{cid}")
def update_cable_type(cid: int, body: CableTypeIn, me: Principal = Depends(require_admin)):
    r = db.row("SELECT * FROM cable_types WHERE id = ?", (cid,))
    if not r:
        raise HTTPException(404, "Kabelart nicht gefunden")
    if body.name.strip().lower() != r["name"].lower():
        raise HTTPException(400, "Der Name einer Kabelart kann nicht geändert werden (bestehende Kabel verweisen darauf). "
                                 "Legen Sie stattdessen eine neue Kabelart an und deaktivieren Sie die alte.")
    _check_cable_type_body(body)
    db.execute("UPDATE cable_types SET category=?, count_label=?, note=?, active=?, sort=? WHERE id=?",
               (body.category, body.count_label.strip(), body.note.strip(), int(body.active), body.sort, cid))
    audit.log(me.name, "cabletype.update", "cable_type", cid, r["name"])
    return _cable_type_out(db.row("SELECT * FROM cable_types WHERE id = ?", (cid,)))


@router.delete("/cable-types/{cid}")
def delete_cable_type(cid: int, me: Principal = Depends(require_admin)):
    r = db.row("SELECT * FROM cable_types WHERE id = ?", (cid,))
    if not r:
        raise HTTPException(404, "Kabelart nicht gefunden")
    if r["builtin"]:
        raise HTTPException(409, "Mitgelieferte Kabelarten können nicht gelöscht, nur deaktiviert werden")
    if _cable_type_out(r)["in_use"]:
        raise HTTPException(409, "Die Kabelart wird noch verwendet und kann nur deaktiviert werden")
    db.execute("DELETE FROM cable_types WHERE id = ?", (cid,))
    audit.log(me.name, "cabletype.delete", "cable_type", cid, r["name"])
    return {"ok": True}


# ── Gerätemodelle ─────────────────────────────────────────────────────────────

def _model_out(r: dict) -> dict:
    r = dict(r)
    r["ports"] = json.loads(r["ports"] or "[]")
    r["port_total"] = sum(g["count"] * (2 if g.get("dual") else 1) for g in r["ports"])
    r["active"] = bool(r["active"])
    r["device_count"] = db.row("SELECT COUNT(*) AS n FROM devices WHERE model_id = ?", (r["id"],))["n"]
    return r


def _check_model(body: DeviceModelIn) -> str:
    if body.type not in DEVICE_TYPES:
        raise HTTPException(400, f"Typ '{body.type}' ist ungültig (erlaubt: {', '.join(DEVICE_TYPES)})")
    body.side_slot = check_mount(body.orientation, body.mount_side, body.side_slot)
    total = 0
    for g in body.ports:
        if g.medium not in PORT_MEDIA:
            raise HTTPException(400, f"Medium '{g.medium}' ist ungültig (erlaubt: {', '.join(PORT_MEDIA)})")
        total += g.count * (2 if g.dual else 1)
    if total > MAX_TEMPLATE_PORTS:
        raise HTTPException(400, f"Die Vorlage erzeugt {total} Ports (höchstens {MAX_TEMPLATE_PORTS})")
    return json.dumps([g.model_dump() for g in body.ports], ensure_ascii=False)


@router.get("/device-models")
def list_models(q: str = "", type: str = "", orientation: str = "", all: bool = False, _: Principal = Depends(current_principal)):
    where, args = [], []
    if not all:
        where.append("active = 1")
    types = [t for t in type.split(",") if t]                       # ein Typ oder mehrere, durch Komma getrennt
    if types:
        where.append(f"type IN ({','.join('?' * len(types))})"); args += types
    if orientation in ("horizontal", "vertical"):
        where.append("orientation = ?"); args.append(orientation)
    if q.strip():
        where.append("(vendor LIKE ? OR model LIKE ? OR article_no LIKE ? OR description LIKE ?)"); args += [f"%{q.strip()}%"] * 4
    w = ("WHERE " + " AND ".join(where)) if where else ""
    return [_model_out(r) for r in db.rows(f"SELECT * FROM device_models {w} ORDER BY vendor COLLATE NOCASE, model COLLATE NOCASE", tuple(args))]


@router.get("/device-models/{mid}")
def get_model(mid: int, _: Principal = Depends(current_principal)):
    r = db.row("SELECT * FROM device_models WHERE id = ?", (mid,))
    if not r:
        raise HTTPException(404, "Modell nicht gefunden")
    return _model_out(r)


@router.post("/device-models", status_code=201)
def create_model(body: DeviceModelIn, me: Principal = Depends(require_master_write)):
    ports = _check_model(body)
    now = time.time()
    try:
        mid = db.execute(
            """INSERT INTO device_models(vendor, model, type, height_u, article_no, description, ports, note, active,
                                         mount_side, orientation, side_slot, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (body.vendor.strip(), body.model.strip(), body.type, body.height_u, body.article_no.strip(),
             body.description.strip(), ports, body.note.strip(), int(body.active), body.mount_side, body.orientation, body.side_slot, now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Das Modell '{body.vendor} {body.model}' existiert bereits")
    audit.log(me.name, "model.create", "device_model", mid, f"{body.vendor} {body.model}")
    return _model_out(db.row("SELECT * FROM device_models WHERE id = ?", (mid,)))


@router.put("/device-models/{mid}")
def update_model(mid: int, body: DeviceModelIn, me: Principal = Depends(require_master_write)):
    if not db.row("SELECT id FROM device_models WHERE id = ?", (mid,)):
        raise HTTPException(404, "Modell nicht gefunden")
    ports = _check_model(body)
    try:
        db.execute(
            """UPDATE device_models SET vendor=?, model=?, type=?, height_u=?, article_no=?, description=?, ports=?, note=?,
                                        active=?, mount_side=?, orientation=?, side_slot=?, updated_at=? WHERE id=?""",
            (body.vendor.strip(), body.model.strip(), body.type, body.height_u, body.article_no.strip(),
             body.description.strip(), ports, body.note.strip(), int(body.active), body.mount_side, body.orientation, body.side_slot, time.time(), mid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Das Modell '{body.vendor} {body.model}' existiert bereits")
    audit.log(me.name, "model.update", "device_model", mid, f"{body.vendor} {body.model}")
    return _model_out(db.row("SELECT * FROM device_models WHERE id = ?", (mid,)))


@router.delete("/device-models/{mid}")
def delete_model(mid: int, me: Principal = Depends(require_master_write)):
    r = db.row("SELECT * FROM device_models WHERE id = ?", (mid,))
    if not r:
        raise HTTPException(404, "Modell nicht gefunden")
    if _model_out(r)["device_count"]:
        raise HTTPException(409, "Das Modell wird von Geräten verwendet und kann nur deaktiviert werden")
    db.execute("DELETE FROM device_models WHERE id = ?", (mid,))
    audit.log(me.name, "model.delete", "device_model", mid, f"{r['vendor']} {r['model']}")
    return {"ok": True}
