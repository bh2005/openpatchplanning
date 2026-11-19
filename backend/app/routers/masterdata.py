"""Standorte, Locations (Gebäude/Etage/Raum/Rack), Geräte und Ports."""
from __future__ import annotations

import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, db
from ..auth import Principal, current_principal, require_master_write
from ..schemas import (DEVICE_STATUS, DEVICE_TYPES, LOCATION_KINDS, PORT_MEDIA, DeviceIn, LocationIn, PeerIn,
                       PortBulkIn, PortIn, SiteIn)

router = APIRouter(prefix="/api", tags=["stammdaten"])


def _one_of(value: str, allowed: tuple, label: str) -> str:
    if value not in allowed:
        raise HTTPException(400, f"{label}: '{value}' ist ungültig (erlaubt: {', '.join(allowed)})")
    return value


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name or "")]


def sort_ports(ports: list[dict]) -> list[dict]:
    """Natürliche Sortierung nach Portname (Gi1/0/2 vor Gi1/0/10)."""
    return sorted(ports, key=lambda p: _natural_key(p["name"]))


# ── Standorte ─────────────────────────────────────────────────────────────────

@router.get("/sites")
def list_sites(_: Principal = Depends(current_principal)):
    return db.rows("""SELECT s.*, (SELECT COUNT(*) FROM locations l WHERE l.site_id = s.id) AS locations,
                             (SELECT COUNT(*) FROM devices d JOIN locations l ON l.id = d.location_id WHERE l.site_id = s.id) AS devices
                      FROM sites s ORDER BY s.code""")


@router.post("/sites", status_code=201)
def create_site(body: SiteIn, me: Principal = Depends(require_master_write)):
    try:
        sid = db.execute("INSERT INTO sites(code, name, address, note) VALUES (?,?,?,?)",
                         (body.code.strip(), body.name.strip(), body.address.strip(), body.note.strip()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Standortcode '{body.code}' existiert bereits")
    audit.log(me.name, "site.create", "site", sid, body.code)
    return db.row("SELECT * FROM sites WHERE id = ?", (sid,))


@router.put("/sites/{sid}")
def update_site(sid: int, body: SiteIn, me: Principal = Depends(require_master_write)):
    if not db.row("SELECT id FROM sites WHERE id = ?", (sid,)):
        raise HTTPException(404, "Standort nicht gefunden")
    try:
        db.execute("UPDATE sites SET code=?, name=?, address=?, note=? WHERE id=?",
                   (body.code.strip(), body.name.strip(), body.address.strip(), body.note.strip(), sid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Standortcode '{body.code}' existiert bereits")
    audit.log(me.name, "site.update", "site", sid, body.code)
    return db.row("SELECT * FROM sites WHERE id = ?", (sid,))


@router.delete("/sites/{sid}")
def delete_site(sid: int, me: Principal = Depends(require_master_write)):
    s = db.row("SELECT * FROM sites WHERE id = ?", (sid,))
    if not s:
        raise HTTPException(404, "Standort nicht gefunden")
    n = db.row("SELECT COUNT(*) AS n FROM devices d JOIN locations l ON l.id = d.location_id WHERE l.site_id = ?", (sid,))["n"]
    if n:
        raise HTTPException(409, f"Der Standort enthält noch {n} Gerät(e) – diese zuerst verschieben oder löschen")
    db.execute("DELETE FROM sites WHERE id = ?", (sid,))
    audit.log(me.name, "site.delete", "site", sid, s["code"])
    return {"ok": True}


# ── Locations ─────────────────────────────────────────────────────────────────

def location_path(location_id: Optional[int]) -> str:
    """„Standort / Gebäude / Raum / Rack“ für eine Location."""
    if not location_id:
        return ""
    parts: list[str] = []
    cur = db.row("SELECT * FROM locations WHERE id = ?", (location_id,))
    site = db.row("SELECT code FROM sites WHERE id = ?", (cur["site_id"],)) if cur else None
    guard = 0
    while cur and guard < 20:
        parts.append(cur["name"])
        cur = db.row("SELECT * FROM locations WHERE id = ?", (cur["parent_id"],)) if cur["parent_id"] else None
        guard += 1
    if site:
        parts.append(site["code"])
    return " / ".join(reversed(parts))


def _check_location(body: LocationIn, own_id: Optional[int] = None) -> None:
    _one_of(body.kind, LOCATION_KINDS, "Art")
    if not db.row("SELECT id FROM sites WHERE id = ?", (body.site_id,)):
        raise HTTPException(400, "Standort nicht gefunden")
    if body.kind != "rack" and body.rack_units is not None:
        raise HTTPException(400, "Höheneinheiten gibt es nur bei Racks")
    if body.parent_id:
        p = db.row("SELECT * FROM locations WHERE id = ?", (body.parent_id,))
        if not p or p["site_id"] != body.site_id:
            raise HTTPException(400, "Die übergeordnete Location muss zum selben Standort gehören")
        if own_id:                                  # Zyklus verhindern
            cur, guard = p, 0
            while cur and guard < 20:
                if cur["id"] == own_id:
                    raise HTTPException(400, "Eine Location kann nicht in sich selbst enthalten sein")
                cur = db.row("SELECT * FROM locations WHERE id = ?", (cur["parent_id"],)) if cur["parent_id"] else None
                guard += 1


@router.get("/locations")
def list_locations(site_id: Optional[int] = None, _: Principal = Depends(current_principal)):
    sql = "SELECT l.*, (SELECT COUNT(*) FROM devices d WHERE d.location_id = l.id) AS devices FROM locations l"
    rows = db.rows(sql + (" WHERE l.site_id = ?" if site_id else "") + " ORDER BY l.site_id, l.parent_id, l.name",
                   (site_id,) if site_id else ())
    for r in rows:
        r["path"] = location_path(r["id"])
    return rows


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, me: Principal = Depends(require_master_write)):
    _check_location(body)
    lid = db.execute("INSERT INTO locations(site_id, parent_id, kind, name, rack_units, note) VALUES (?,?,?,?,?,?)",
                     (body.site_id, body.parent_id, body.kind, body.name.strip(), body.rack_units, body.note.strip()))
    audit.log(me.name, "location.create", "location", lid, f"{body.kind} {body.name}")
    return {**db.row("SELECT * FROM locations WHERE id = ?", (lid,)), "path": location_path(lid)}


@router.put("/locations/{lid}")
def update_location(lid: int, body: LocationIn, me: Principal = Depends(require_master_write)):
    if not db.row("SELECT id FROM locations WHERE id = ?", (lid,)):
        raise HTTPException(404, "Location nicht gefunden")
    _check_location(body, own_id=lid)
    db.execute("UPDATE locations SET site_id=?, parent_id=?, kind=?, name=?, rack_units=?, note=? WHERE id=?",
               (body.site_id, body.parent_id, body.kind, body.name.strip(), body.rack_units, body.note.strip(), lid))
    audit.log(me.name, "location.update", "location", lid, body.name)
    return {**db.row("SELECT * FROM locations WHERE id = ?", (lid,)), "path": location_path(lid)}


@router.delete("/locations/{lid}")
def delete_location(lid: int, me: Principal = Depends(require_master_write)):
    loc = db.row("SELECT * FROM locations WHERE id = ?", (lid,))
    if not loc:
        raise HTTPException(404, "Location nicht gefunden")
    if db.row("SELECT COUNT(*) AS n FROM locations WHERE parent_id = ?", (lid,))["n"]:
        raise HTTPException(409, "Die Location enthält noch untergeordnete Locations")
    n = db.row("SELECT COUNT(*) AS n FROM devices WHERE location_id = ?", (lid,))["n"]
    if n:
        raise HTTPException(409, f"Die Location enthält noch {n} Gerät(e)")
    db.execute("DELETE FROM locations WHERE id = ?", (lid,))
    audit.log(me.name, "location.delete", "location", lid, loc["name"])
    return {"ok": True}


# ── Geräte ────────────────────────────────────────────────────────────────────

def _location_and_children(location_id: int) -> list[int]:
    ids, todo = [], [location_id]
    while todo:
        cur = todo.pop()
        ids.append(cur)
        todo += [r["id"] for r in db.rows("SELECT id FROM locations WHERE parent_id = ?", (cur,))]
    return ids


def _device_out(d: dict) -> dict:
    d["location_path"] = location_path(d["location_id"])
    d["port_count"] = db.row("SELECT COUNT(*) AS n FROM ports WHERE device_id = ?", (d["id"],))["n"]
    return d


@router.get("/devices")
def list_devices(
    q: str = "", type: str = "", status: str = "", source: str = "",
    site_id: Optional[int] = None, location_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    _: Principal = Depends(current_principal),
):
    where, args = [], []
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(d.hostname LIKE ? OR d.model LIKE ? OR d.serial LIKE ? OR d.mgmt_ip LIKE ? OR d.note LIKE ?)")
        args += [like] * 5
    for col, val in (("type", type), ("status", status), ("source", source)):
        if val:
            where.append(f"d.{col} = ?"); args.append(val)
    if location_id:
        ids = _location_and_children(location_id)
        where.append(f"d.location_id IN ({','.join('?' * len(ids))})"); args += ids
    elif site_id:
        where.append("d.location_id IN (SELECT id FROM locations WHERE site_id = ?)"); args.append(site_id)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.row(f"SELECT COUNT(*) AS n FROM devices d{w}", tuple(args))["n"]
    items = db.rows(f"SELECT d.* FROM devices d{w} ORDER BY d.hostname COLLATE NOCASE LIMIT ? OFFSET ?", (*args, limit, offset))
    return {"total": total, "items": [_device_out(d) for d in items]}


def _check_device(body: DeviceIn) -> None:
    _one_of(body.type, DEVICE_TYPES, "Typ")
    _one_of(body.status, DEVICE_STATUS, "Status")
    if body.location_id and not db.row("SELECT id FROM locations WHERE id = ?", (body.location_id,)):
        raise HTTPException(400, "Location nicht gefunden")
    if body.rack_position and not body.location_id:
        raise HTTPException(400, "Eine HE-Position braucht eine Location (Rack)")


@router.get("/devices/{did}")
def get_device(did: int, _: Principal = Depends(current_principal)):
    d = db.row("SELECT * FROM devices WHERE id = ?", (did,))
    if not d:
        raise HTTPException(404, "Gerät nicht gefunden")
    d = _device_out(d)
    d["ports"] = sort_ports(db.rows("SELECT * FROM ports WHERE device_id = ?", (did,)))
    return d


@router.post("/devices", status_code=201)
def create_device(body: DeviceIn, me: Principal = Depends(require_master_write)):
    _check_device(body)
    now = time.time()
    try:
        did = db.execute(
            """INSERT INTO devices(hostname, type, vendor, model, serial, mgmt_ip, location_id, rack_position, status,
                                   source, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (body.hostname.strip(), body.type, body.vendor.strip(), body.model.strip(), body.serial.strip(), body.mgmt_ip.strip(),
             body.location_id, body.rack_position, body.status, "manual", body.note.strip(), now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{body.hostname}' existiert bereits")
    audit.log(me.name, "device.create", "device", did, body.hostname)
    return _device_out(db.row("SELECT * FROM devices WHERE id = ?", (did,)))


@router.put("/devices/{did}")
def update_device(did: int, body: DeviceIn, me: Principal = Depends(require_master_write)):
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _check_device(body)
    try:
        db.execute(
            """UPDATE devices SET hostname=?, type=?, vendor=?, model=?, serial=?, mgmt_ip=?, location_id=?, rack_position=?,
                                  status=?, note=?, updated_at=? WHERE id=?""",
            (body.hostname.strip(), body.type, body.vendor.strip(), body.model.strip(), body.serial.strip(), body.mgmt_ip.strip(),
             body.location_id, body.rack_position, body.status, body.note.strip(), time.time(), did))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{body.hostname}' existiert bereits")
    audit.log(me.name, "device.update", "device", did, body.hostname)
    return _device_out(db.row("SELECT * FROM devices WHERE id = ?", (did,)))


@router.delete("/devices/{did}")
def delete_device(did: int, me: Principal = Depends(require_master_write)):
    d = db.row("SELECT * FROM devices WHERE id = ?", (did,))
    if not d:
        raise HTTPException(404, "Gerät nicht gefunden")
    db.execute("DELETE FROM devices WHERE id = ?", (did,))          # Ports werden mit gelöscht (ON DELETE CASCADE)
    audit.log(me.name, "device.delete", "device", did, d["hostname"])
    return {"ok": True}


# ── Ports ─────────────────────────────────────────────────────────────────────

def _check_port(body: PortIn) -> None:
    _one_of(body.medium, PORT_MEDIA, "Medium")


@router.get("/devices/{did}/ports")
def list_ports(did: int, _: Principal = Depends(current_principal)):
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    return sort_ports(db.rows("SELECT * FROM ports WHERE device_id = ?", (did,)))


@router.post("/devices/{did}/ports", status_code=201)
def create_port(did: int, body: PortIn, me: Principal = Depends(require_master_write)):
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _check_port(body)
    try:
        pid = db.execute(
            """INSERT INTO ports(device_id, name, idx, medium, speed_mbps, description, admin_status, oper_status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (did, body.name.strip(), body.idx, body.medium, body.speed_mbps, body.description.strip(),
             body.admin_status, body.oper_status))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Port '{body.name}' existiert an diesem Gerät bereits")
    audit.log(me.name, "port.create", "port", pid, f"device {did}: {body.name}")
    return db.row("SELECT * FROM ports WHERE id = ?", (pid,))


@router.post("/devices/{did}/ports/bulk", status_code=201)
def create_ports_bulk(did: int, body: PortBulkIn, me: Principal = Depends(require_master_write)):
    """Legt count Ports an: <prefix><start> … <prefix><start+count-1>. Bereits vorhandene Namen werden übersprungen."""
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _one_of(body.medium, PORT_MEDIA, "Medium")
    created = skipped = 0
    for i in range(body.start, body.start + body.count):
        try:
            db.execute("INSERT INTO ports(device_id, name, idx, medium, speed_mbps) VALUES (?,?,?,?,?)",
                       (did, f"{body.prefix}{i}", i, body.medium, body.speed_mbps))
            created += 1
        except sqlite3.IntegrityError:
            skipped += 1
    audit.log(me.name, "port.bulk_create", "device", did, f"{body.prefix}{body.start}..: {created} angelegt, {skipped} übersprungen")
    return {"created": created, "skipped": skipped}


@router.put("/ports/{pid}")
def update_port(pid: int, body: PortIn, me: Principal = Depends(require_master_write)):
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    _check_port(body)
    try:
        db.execute(
            """UPDATE ports SET name=?, idx=?, medium=?, speed_mbps=?, description=?, admin_status=?, oper_status=? WHERE id=?""",
            (body.name.strip(), body.idx, body.medium, body.speed_mbps, body.description.strip(),
             body.admin_status, body.oper_status, pid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Port '{body.name}' existiert an diesem Gerät bereits")
    audit.log(me.name, "port.update", "port", pid, body.name)
    return db.row("SELECT * FROM ports WHERE id = ?", (pid,))


@router.delete("/ports/{pid}")
def delete_port(pid: int, me: Principal = Depends(require_master_write)):
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    db.execute("DELETE FROM ports WHERE id = ?", (pid,))
    audit.log(me.name, "port.delete", "port", pid, p["name"])
    return {"ok": True}


@router.put("/ports/{pid}/peer")
def set_peer(pid: int, body: PeerIn, me: Principal = Depends(require_master_write)):
    """Durchschleifung (z. B. Vorder-/Rückseite eines Patchfelds): symmetrisch, nur innerhalb desselben Geräts."""
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    if p["peer_port_id"]:                                                   # bisherige Verknüpfung lösen
        db.execute("UPDATE ports SET peer_port_id = NULL WHERE id IN (?, ?)", (pid, p["peer_port_id"]))
    if body.peer_port_id:
        q = db.row("SELECT * FROM ports WHERE id = ?", (body.peer_port_id,))
        if not q:
            raise HTTPException(404, "Gegenport nicht gefunden")
        if q["id"] == pid:
            raise HTTPException(400, "Ein Port kann nicht mit sich selbst durchgeschleift werden")
        if q["device_id"] != p["device_id"]:
            raise HTTPException(400, "Durchgeschleifte Ports müssen zum selben Gerät gehören")
        if q["peer_port_id"]:
            db.execute("UPDATE ports SET peer_port_id = NULL WHERE id = ?", (q["peer_port_id"],))
        db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (q["id"], pid))
        db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (pid, q["id"]))
    audit.log(me.name, "port.peer", "port", pid, f"-> {body.peer_port_id}")
    return db.row("SELECT * FROM ports WHERE id = ?", (pid,))
