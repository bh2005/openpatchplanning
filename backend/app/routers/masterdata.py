"""Standorte, Locations (Gebäude/Etage/Raum/Rack), Geräte und Ports."""
from __future__ import annotations

import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, db
from ..auth import Principal, current_principal, require_master_write
from ..schemas import (CABLE_TYPES, DEVICE_STATUS, DEVICE_TYPES, LOCATION_KINDS, PORT_MEDIA, CableIn, DeviceIn,
                       LocationIn, PeerIn, PortBulkIn, PortIn, SiteIn)

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


def _check_device(body: DeviceIn, own_id: Optional[int] = None) -> None:
    _one_of(body.type, DEVICE_TYPES, "Typ")
    _one_of(body.status, DEVICE_STATUS, "Status")
    loc = db.row("SELECT * FROM locations WHERE id = ?", (body.location_id,)) if body.location_id else None
    if body.location_id and not loc:
        raise HTTPException(400, "Location nicht gefunden")
    if body.rack_position:
        if not loc:
            raise HTTPException(400, "Eine HE-Position braucht eine Location (Rack)")
        if loc["kind"] != "rack":
            raise HTTPException(400, "Eine HE-Position ist nur in einem Rack möglich")
        top = body.rack_position + body.height_u - 1
        if loc["rack_units"] and top > loc["rack_units"]:
            raise HTTPException(400, f"Das Gerät passt nicht ins Rack ({loc['rack_units']} HE): belegt HE {body.rack_position}–{top}")
        for o in db.rows("SELECT id, hostname, rack_position, height_u FROM devices WHERE location_id = ? AND rack_position IS NOT NULL",
                         (loc["id"],)):
            if o["id"] != own_id and not (top < o["rack_position"] or o["rack_position"] + o["height_u"] - 1 < body.rack_position):
                raise HTTPException(409, f"HE {body.rack_position}–{top} überschneidet sich mit {o['hostname']} "
                                         f"(HE {o['rack_position']}–{o['rack_position'] + o['height_u'] - 1})")


@router.get("/devices/{did}")
def get_device(did: int, _: Principal = Depends(current_principal)):
    d = db.row("SELECT * FROM devices WHERE id = ?", (did,))
    if not d:
        raise HTTPException(404, "Gerät nicht gefunden")
    d = _device_out(d)
    d["ports"] = sort_ports(_ports_with_cables(db.rows("SELECT * FROM ports WHERE device_id = ?", (did,))))
    return d


@router.post("/devices", status_code=201)
def create_device(body: DeviceIn, me: Principal = Depends(require_master_write)):
    _check_device(body)
    now = time.time()
    try:
        did = db.execute(
            """INSERT INTO devices(hostname, type, vendor, model, serial, mgmt_ip, location_id, rack_position, height_u, status,
                                   source, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (body.hostname.strip(), body.type, body.vendor.strip(), body.model.strip(), body.serial.strip(), body.mgmt_ip.strip(),
             body.location_id, body.rack_position, body.height_u, body.status, "manual", body.note.strip(), now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{body.hostname}' existiert bereits")
    audit.log(me.name, "device.create", "device", did, body.hostname)
    return _device_out(db.row("SELECT * FROM devices WHERE id = ?", (did,)))


@router.put("/devices/{did}")
def update_device(did: int, body: DeviceIn, me: Principal = Depends(require_master_write)):
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _check_device(body, own_id=did)
    try:
        db.execute(
            """UPDATE devices SET hostname=?, type=?, vendor=?, model=?, serial=?, mgmt_ip=?, location_id=?, rack_position=?,
                                  height_u=?, status=?, note=?, updated_at=? WHERE id=?""",
            (body.hostname.strip(), body.type, body.vendor.strip(), body.model.strip(), body.serial.strip(), body.mgmt_ip.strip(),
             body.location_id, body.rack_position, body.height_u, body.status, body.note.strip(), time.time(), did))
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


def _port_with_cable(port: dict) -> dict:
    """Reichert einen Port-Dict mit Kabel-Info und Peer-Name an."""
    out = dict(port)
    if port.get("peer_port_id"):
        peer = db.row("SELECT name FROM ports WHERE id = ?", (port["peer_port_id"],))
        out["peer_port_name"] = peer["name"] if peer else None
    else:
        out["peer_port_name"] = None
    cable = db.row(
        """SELECT c.*,
                  CASE WHEN c.port_a_id = :pid THEN c.port_b_id ELSE c.port_a_id END AS other_port_id
           FROM cables c WHERE c.port_a_id = :pid OR c.port_b_id = :pid""",
        {"pid": port["id"]}
    )
    if cable:
        other = db.row(
            """SELECT p.id, p.name, p.device_id, d.hostname
               FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?""",
            (cable["other_port_id"],)
        )
        out["cable"] = {
            "id": cable["id"],
            "cable_label": cable["cable_label"],
            "cable_type": cable["cable_type"],
            "fiber_count": cable["fiber_count"],
            "length_m": cable["length_m"],
            "color": cable["color"],
            "installed_at": cable["installed_at"],
            "measurement_ref": cable["measurement_ref"],
            "measurement_ok": None if cable["measurement_ok"] is None else bool(cable["measurement_ok"]),
            "note": cable["note"],
            "port_id": other["id"],
            "port_name": other["name"],
            "device_id": other["device_id"],
            "device_hostname": other["hostname"],
        }
    else:
        out["cable"] = None
    return out


def _ports_with_cables(ports: list[dict]) -> list[dict]:
    return [_port_with_cable(p) for p in ports]


@router.get("/devices/{did}/ports")
def list_ports(did: int, _: Principal = Depends(current_principal)):
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    return sort_ports(_ports_with_cables(db.rows("SELECT * FROM ports WHERE device_id = ?", (did,))))


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
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))


@router.post("/devices/{did}/ports/bulk", status_code=201)
def create_ports_bulk(did: int, body: PortBulkIn, me: Principal = Depends(require_master_write)):
    """Legt count Ports an. dual=True erzeugt je einen Vorder- (<prefix><n>) und Rückseiten-Port (<prefix><n><back_suffix>)
    und setzt automatisch den Peer zwischen beiden."""
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _one_of(body.medium, PORT_MEDIA, "Medium")
    created = skipped = 0
    for i in range(body.start, body.start + body.count):
        front_name = f"{body.prefix}{i}"
        try:
            front_id = db.execute("INSERT INTO ports(device_id, name, idx, medium, speed_mbps) VALUES (?,?,?,?,?)",
                                  (did, front_name, i, body.medium, body.speed_mbps))
            created += 1
        except sqlite3.IntegrityError:
            front_id = None
            skipped += 1
        if body.dual:
            back_name = f"{body.prefix}{i}{body.back_suffix}"
            try:
                back_id = db.execute("INSERT INTO ports(device_id, name, idx, medium, speed_mbps) VALUES (?,?,?,?,?)",
                                     (did, back_name, i, body.medium, body.speed_mbps))
                created += 1
                if front_id:
                    db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (back_id, front_id))
                    db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (front_id, back_id))
            except sqlite3.IntegrityError:
                skipped += 1
    audit.log(me.name, "port.bulk_create", "device", did,
              f"{body.prefix}{body.start}..: {created} angelegt, {skipped} übersprungen" + (" (dual)" if body.dual else ""))
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
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))


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
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))


@router.get("/cables")
def list_cables(
    cable_type: Optional[str] = None,
    measurement_ok: Optional[str] = None,
    q: Optional[str] = None,
    _: Principal = Depends(current_principal),
):
    """Alle Kabel, optional gefiltert nach Typ, Messstatus oder Kabelnummer."""
    where, args = [], []
    if cable_type:
        where.append("c.cable_type = ?"); args.append(cable_type)
    if measurement_ok == "yes":
        where.append("c.measurement_ok = 1")
    elif measurement_ok == "no":
        where.append("c.measurement_ok = 0")
    elif measurement_ok == "none":
        where.append("c.measurement_ok IS NULL")
    if q:
        where.append("(c.cable_label LIKE ? OR c.note LIKE ? OR c.measurement_ref LIKE ?)")
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.rows(
        f"""SELECT c.*,
                   pa.name AS port_a_name, da.hostname AS device_a_hostname, da.id AS device_a_id,
                   pb.name AS port_b_name, db_.hostname AS device_b_hostname, db_.id AS device_b_id
            FROM cables c
            JOIN ports pa ON pa.id = c.port_a_id
            JOIN devices da ON da.id = pa.device_id
            JOIN ports pb ON pb.id = c.port_b_id
            JOIN devices db_ ON db_.id = pb.device_id
            {w}
            ORDER BY c.cable_label COLLATE NOCASE, c.id""",
        tuple(args),
    )
    return [_cable_out(r) for r in rows]


def _cable_out(c: dict) -> dict:
    return {
        "id": c["id"],
        "cable_label": c["cable_label"],
        "cable_type": c["cable_type"],
        "fiber_count": c["fiber_count"],
        "length_m": c["length_m"],
        "color": c["color"],
        "installed_at": c["installed_at"],
        "measurement_ref": c["measurement_ref"],
        "measurement_ok": None if c["measurement_ok"] is None else bool(c["measurement_ok"]),
        "note": c["note"],
        "created_by": c["created_by"],
        "created_at": c["created_at"],
        "port_a": {"id": c["port_a_id"], "name": c["port_a_name"],
                   "device_id": c["device_a_id"], "device_hostname": c["device_a_hostname"]},
        "port_b": {"id": c["port_b_id"], "name": c["port_b_name"],
                   "device_id": c["device_b_id"], "device_hostname": c["device_b_hostname"]},
        "workorder_id": c.get("workorder_id"),
    }


@router.put("/cables/{cid}")
def update_cable(cid: int, body: CableIn, me: Principal = Depends(require_master_write)):
    """Kabelattribute aktualisieren (ohne die Port-Verbindung zu ändern)."""
    c = db.row("SELECT * FROM cables WHERE id = ?", (cid,))
    if not c:
        raise HTTPException(404, "Kabel nicht gefunden")
    _one_of(body.cable_type, CABLE_TYPES, "Kabeltyp")
    db.execute(
        """UPDATE cables SET cable_label=?, cable_type=?, fiber_count=?, length_m=?, color=?,
                             installed_at=?, measurement_ref=?, measurement_ok=?, note=? WHERE id=?""",
        (body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
         body.color.strip(), body.installed_at, body.measurement_ref.strip(),
         None if body.measurement_ok is None else int(body.measurement_ok),
         body.note.strip(), cid),
    )
    audit.log(me.name, "cable.update", "cable", cid, body.cable_label)
    row = db.row(
        """SELECT c.*,
                  pa.name AS port_a_name, da.hostname AS device_a_hostname, da.id AS device_a_id,
                  pb.name AS port_b_name, db_.hostname AS device_b_hostname, db_.id AS device_b_id
           FROM cables c
           JOIN ports pa ON pa.id = c.port_a_id JOIN devices da ON da.id = pa.device_id
           JOIN ports pb ON pb.id = c.port_b_id JOIN devices db_ ON db_.id = pb.device_id
           WHERE c.id = ?""", (cid,))
    return _cable_out(row)


@router.put("/ports/{pid}/cable")
def set_cable(pid: int, body: CableIn, me: Principal = Depends(require_master_write)):
    """Verbindet zwei Ports mit einem Kabel (symmetrisch). port_b_id=None löst die Verbindung."""
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    _one_of(body.cable_type, CABLE_TYPES, "Kabeltyp")
    db.execute("DELETE FROM cables WHERE port_a_id = ? OR port_b_id = ?", (pid, pid))
    if body.port_b_id:
        q = db.row("SELECT * FROM ports WHERE id = ?", (body.port_b_id,))
        if not q:
            raise HTTPException(404, "Zielport nicht gefunden")
        if q["id"] == pid:
            raise HTTPException(400, "Ein Port kann nicht mit sich selbst verbunden werden")
        db.execute("DELETE FROM cables WHERE port_a_id = ? OR port_b_id = ?", (q["id"], q["id"]))
        a, b = (pid, q["id"]) if pid < q["id"] else (q["id"], pid)
        db.execute(
            """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m,
                                  color, installed_at, measurement_ref, measurement_ok, note, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a, b, body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
             body.color.strip(), body.installed_at,
             body.measurement_ref.strip(),
             None if body.measurement_ok is None else int(body.measurement_ok),
             body.note.strip(), me.name, time.time()),
        )
    audit.log(me.name, "cable.set", "port", pid, f"-> {body.port_b_id} [{body.cable_label}]")
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))
