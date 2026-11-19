"""Import von Geräten und Ports (CSV, JSON, API, Checkmk) – eine gemeinsame Logik.

Regeln
  * **Idempotent:** ein Gerät wird zuerst über (source, ext_id), sonst über den Hostnamen (Groß-/Kleinschreibung egal) gefunden.
  * Es werden nur **Geräte und Ports** angelegt/aktualisiert – bestehende Verbindungen ändern ausschließlich Aufträge.
  * Felder, die in der Quelle **leer** sind, überschreiben vorhandene Werte nicht. Ports, die in der Quelle fehlen, werden nicht gelöscht.
  * **Trockenlauf:** alles wird berechnet und gemeldet, aber nichts gespeichert.
  * **Atomar** (Standard): gibt es mindestens einen Fehler, wird *nichts* gespeichert.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
from typing import Any, Optional

from . import db
from .schemas import DEVICE_STATUS, DEVICE_TYPES, LOCATION_KINDS, PORT_MEDIA

MAX_ITEMS_IN_RESULT = 1000
DEFAULT_LOCATION = "Allgemein"         # Standard-Location, wenn nur ein Standortcode angegeben ist

TYPE_ALIASES = {
    "sw": "switch", "accesspoint": "ap", "wlan": "ap", "wap": "ap", "fw": "firewall",
    "patchfeld": "patchpanel", "patchpanel": "patchpanel", "pp": "patchpanel", "dose": "outlet", "wanddose": "outlet",
    "steckdose": "outlet", "rt": "router", "srv": "server", "host": "server", "pc": "endpoint", "client": "endpoint",
    "drucker": "endpoint", "printer": "endpoint", "telefon": "endpoint", "phone": "endpoint",
}
STATUS_ALIASES = {"geplant": "planned", "aktiv": "active", "active": "active", "ausser betrieb": "retired",
                  "außer betrieb": "retired", "retired": "retired", "decommissioned": "retired"}
MEDIUM_ALIASES = {"rj45": "RJ45", "kupfer": "RJ45", "copper": "RJ45", "sfp": "SFP", "sfp+": "SFP+", "sfpplus": "SFP+",
                  "sfp28": "SFP28", "qsfp": "QSFP", "lwl": "LWL", "fiber": "LWL", "fibre": "LWL", "glasfaser": "LWL"}

DEVICE_FIELDS = ["hostname", "type", "vendor", "model", "serial", "mgmt_ip", "location", "status", "note", "ext_id"]
PORT_FIELDS = ["hostname", "port", "idx", "medium", "speed_mbps", "description", "admin_status", "oper_status"]
REQUIRED = {"devices": ["hostname"], "ports": ["hostname", "port"]}

ALIASES = {
    "hostname": ["hostname", "host", "name", "geraet", "gerat", "device", "devicename", "geraetename", "switch"],
    "type": ["type", "typ", "devicetype", "geraetetyp", "kind", "art"],
    "vendor": ["vendor", "hersteller", "manufacturer", "make", "brand"],
    "model": ["model", "modell", "modelid", "produkt", "product"],
    "serial": ["serial", "seriennummer", "serialnumber", "sn", "serialno"],
    "mgmt_ip": ["ip", "ipaddress", "ipadresse", "mgmtip", "managementip", "address", "adresse", "mgmtaddress"],
    "location": ["location", "standort", "ort", "raum", "room", "site", "rack"],
    "status": ["status", "state", "zustand"],
    "note": ["note", "notiz", "bemerkung", "comment", "kommentar", "notes"],
    "ext_id": ["extid", "externalid", "id", "uuid", "assetid", "assettag"],
    "port": ["port", "portname", "interface", "ifname", "schnittstelle", "name"],
    "idx": ["idx", "index", "ifindex", "portindex", "nr", "portnr"],
    "medium": ["medium", "mediatype", "porttype", "typ", "type"],
    "speed_mbps": ["speed", "speedmbps", "geschwindigkeit", "bandwidth", "mbit", "mbps"],
    "description": ["description", "beschreibung", "alias", "ifalias", "descr", "label"],
    "admin_status": ["adminstatus", "admin", "ifadminstatus"],
    "oper_status": ["operstatus", "oper", "ifoperstatus", "linkstatus"],
}


def _norm(s: Any) -> str:
    return re.sub(r"[\s_\-.:*]+", "", str(s or "").strip().lower())


# ── CSV ───────────────────────────────────────────────────────────────────────

def decode_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_csv(raw: bytes, delimiter: str = "") -> tuple[list[str], list[dict]]:
    text = decode_csv(raw)
    if not delimiter:
        sample = text[:4096]
        delimiter = max([";", ",", "\t", "|"], key=sample.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    return headers, [{headers[i]: (r[i].strip() if i < len(r) else "") for i in range(len(headers))} for r in rows[1:]]


def suggest_mapping(headers: list[str], kind: str) -> dict[str, str]:
    """Ordnet Spaltenüberschriften den Feldern zu (Feld -> Spaltenname); ein Alias gewinnt nur einmal."""
    fields = DEVICE_FIELDS if kind == "devices" else PORT_FIELDS
    normed = {h: _norm(h) for h in headers}
    mapping: dict[str, str] = {}
    used: set = set()
    for f in fields:
        for alias in ALIASES.get(f, [f]):
            hit = next((h for h, n in normed.items() if n == alias and h not in used), None)
            if hit:
                mapping[f] = hit
                used.add(hit)
                break
    return mapping


def rows_from_csv(raw: bytes, kind: str, mapping: Optional[dict[str, str]] = None, delimiter: str = "") -> tuple[list[dict], dict, list[str]]:
    headers, rows = parse_csv(raw, delimiter)
    mapping = mapping or suggest_mapping(headers, kind)
    missing = [f for f in REQUIRED[kind] if f not in mapping or mapping[f] not in headers]
    if missing:
        raise ValueError(f"Pflichtfeld(er) ohne Spalte: {', '.join(missing)}")
    out = [{f: r.get(col, "") for f, col in mapping.items() if col in headers} for r in rows]
    return out, mapping, headers


def group_port_rows(rows: list[dict]) -> list[dict]:
    """Port-Zeilen (hostname + port …) zu Geräten mit Portliste zusammenfassen."""
    devices: dict[str, dict] = {}
    for r in rows:
        key = str(r.get("hostname", "")).strip().lower()
        d = devices.setdefault(key, {"hostname": str(r.get("hostname", "")).strip(), "ports": [], "_ports_only": True})
        d["ports"].append({"name": r.get("port", ""), "idx": r.get("idx", ""), "medium": r.get("medium", ""),
                           "speed_mbps": r.get("speed_mbps", ""), "description": r.get("description", ""),
                           "admin_status": r.get("admin_status", ""), "oper_status": r.get("oper_status", "")})
    return list(devices.values())


# ── Normalisieren ─────────────────────────────────────────────────────────────

def _int(v: Any) -> Optional[int]:
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(str(v).strip().replace(",", ".")))
    except ValueError:
        raise ValueError(f"'{v}' ist keine Zahl")


def _speed(v: Any) -> Optional[int]:
    """Geschwindigkeit in Mbit/s; akzeptiert 1000, '1G', '10 Gbit/s', '100M'."""
    s = str(v or "").strip().lower().replace(" ", "")
    if not s:
        return None
    m = re.match(r"^([\d.,]+)(g|m)?(?:bit|b)?(?:/?s|ps)?$", s)
    if not m:
        raise ValueError(f"Geschwindigkeit '{v}' nicht lesbar")
    n = float(m.group(1).replace(",", "."))
    return int(n * (1000 if m.group(2) == "g" else 1))


def normalize_port(p: dict) -> dict:
    name = str(p.get("name") or p.get("port") or "").strip()
    if not name:
        raise ValueError("Port ohne Namen")
    medium = str(p.get("medium") or "").strip()
    medium = MEDIUM_ALIASES.get(medium.lower(), medium) if medium else ""
    if medium and medium not in PORT_MEDIA:
        raise ValueError(f"Port {name}: Medium '{medium}' ungültig (erlaubt: {', '.join(PORT_MEDIA)})")
    return {"name": name, "idx": _int(p.get("idx")), "medium": medium, "speed_mbps": _speed(p.get("speed_mbps")),
            "description": str(p.get("description") or "").strip(), "admin_status": str(p.get("admin_status") or "").strip(),
            "oper_status": str(p.get("oper_status") or "").strip(), "ext_id": str(p.get("ext_id") or "").strip()}


def normalize_device(rec: dict) -> dict:
    hostname = str(rec.get("hostname") or "").strip()
    if not hostname:
        raise ValueError("Hostname fehlt")
    typ = str(rec.get("type") or "").strip().lower()
    typ = TYPE_ALIASES.get(typ, typ)
    if typ and typ not in DEVICE_TYPES:
        raise ValueError(f"{hostname}: Typ '{typ}' ungültig (erlaubt: {', '.join(DEVICE_TYPES)})")
    status = str(rec.get("status") or "").strip().lower()
    status = STATUS_ALIASES.get(status, status)
    if status and status not in DEVICE_STATUS:
        raise ValueError(f"{hostname}: Status '{status}' ungültig (erlaubt: {', '.join(DEVICE_STATUS)})")
    ports, seen = [], set()
    for p in rec.get("ports") or []:
        np_ = normalize_port(p)
        if np_["name"].lower() in seen:
            raise ValueError(f"{hostname}: Port '{np_['name']}' kommt doppelt vor")
        seen.add(np_["name"].lower())
        ports.append(np_)
    loc = rec.get("location") or ""
    if isinstance(loc, dict):
        loc = "/".join([str(loc.get("site", ""))] + [str(x) for x in loc.get("path", [])])
    return {"hostname": hostname, "type": typ, "vendor": str(rec.get("vendor") or "").strip(),
            "model": str(rec.get("model") or "").strip(), "serial": str(rec.get("serial") or "").strip(),
            "mgmt_ip": str(rec.get("mgmt_ip") or "").strip(), "status": status, "note": str(rec.get("note") or "").strip(),
            "ext_id": str(rec.get("ext_id") or "").strip(), "location": str(loc).strip(), "ports": ports,
            "ports_only": bool(rec.get("_ports_only"))}


# ── Schreiben (innerhalb einer Transaktion) ───────────────────────────────────

class _Rollback(Exception):
    pass


def _resolve_location(c: sqlite3.Connection, spec: str, create: bool) -> Optional[int]:
    """„SITE/Gebäude/Raum/Rack“ -> location_id; legt fehlende Teile an, wenn create gesetzt ist."""
    parts = [p.strip() for p in re.split(r"[/>]", spec) if p.strip()]
    if not parts:
        return None
    site = c.execute("SELECT * FROM sites WHERE code = ?", (parts[0],)).fetchone()
    if not site:
        if not create:
            raise ValueError(f"Standort '{parts[0]}' existiert nicht")
        sid = c.execute("INSERT INTO sites(code, name) VALUES (?,?)", (parts[0], parts[0])).lastrowid
    else:
        sid = site["id"]
    if len(parts) == 1:                          # nur der Standort: Geräte hängen an einer Location -> Standard-Location „Allgemein“
        parts.append(DEFAULT_LOCATION)
    parent: Optional[int] = None
    for depth, name in enumerate(parts[1:], 1):
        found = c.execute("SELECT id FROM locations WHERE site_id = ? AND name = ? COLLATE NOCASE AND "
                          "(parent_id IS ? OR parent_id = ?)", (sid, name, parent, parent)).fetchone()
        if found:
            parent = found["id"]
            continue
        if not create:
            raise ValueError(f"Location '{name}' existiert nicht")
        is_last = depth == len(parts) - 1
        kind = "rack" if re.match(r"^(rack|rk|schrank)", name.lower()) else ("building" if depth == 1 and not is_last else "room")
        assert kind in LOCATION_KINDS
        parent = c.execute("INSERT INTO locations(site_id, parent_id, kind, name) VALUES (?,?,?,?)", (sid, parent, kind, name)).lastrowid
    return parent


def _apply_one(c: sqlite3.Connection, rec: dict, source: str, create_locations: bool, now: float) -> tuple[str, list[str]]:
    existing = None
    matched_by_ext = False
    if rec["ext_id"]:
        existing = c.execute("SELECT * FROM devices WHERE source = ? AND ext_id = ?", (source, rec["ext_id"])).fetchone()
        matched_by_ext = existing is not None
    if not existing:
        existing = c.execute("SELECT * FROM devices WHERE hostname = ?", (rec["hostname"],)).fetchone()

    loc_id = _resolve_location(c, rec["location"], create_locations) if rec["location"] else None
    changes: list[str] = []

    if not existing:
        did = c.execute(
            """INSERT INTO devices(hostname, type, vendor, model, serial, mgmt_ip, location_id, status, source, ext_id,
                                   last_seen, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rec["hostname"], rec["type"] or "switch", rec["vendor"], rec["model"], rec["serial"], rec["mgmt_ip"], loc_id,
             rec["status"] or "active", source, rec["ext_id"], now, rec["note"], now, now)).lastrowid
        outcome = "created"
        changes.append("Gerät angelegt")
    else:
        did = existing["id"]
        sets, args = [], []
        if matched_by_ext and rec["hostname"].lower() != existing["hostname"].lower():      # in der Quelle umbenannt
            sets.append("hostname = ?"); args.append(rec["hostname"]); changes.append(f"Hostname: {existing['hostname']} → {rec['hostname']}")
        for field in ("type", "vendor", "model", "serial", "mgmt_ip", "status", "note"):
            if rec[field] and rec[field] != existing[field]:
                sets.append(f"{field} = ?"); args.append(rec[field]); changes.append(f"{field}: {existing[field] or '–'} → {rec[field]}")
        if loc_id and loc_id != existing["location_id"]:
            sets.append("location_id = ?"); args.append(loc_id); changes.append("Location geändert")
        if rec["ext_id"] and rec["ext_id"] != existing["ext_id"] and existing["source"] == source:
            sets.append("ext_id = ?"); args.append(rec["ext_id"])
        sets.append("last_seen = ?"); args.append(now)
        if changes:
            sets.append("updated_at = ?"); args.append(now)
        c.execute(f"UPDATE devices SET {', '.join(sets)} WHERE id = ?", (*args, did))
        outcome = "updated" if changes else "unchanged"

    port_new = port_upd = 0
    for p in rec["ports"]:
        ex = c.execute("SELECT * FROM ports WHERE device_id = ? AND name = ?", (did, p["name"])).fetchone()
        if not ex:
            c.execute("""INSERT INTO ports(device_id, name, idx, medium, speed_mbps, description, admin_status, oper_status, ext_id)
                         VALUES (?,?,?,?,?,?,?,?,?)""",
                      (did, p["name"], p["idx"], p["medium"] or "RJ45", p["speed_mbps"], p["description"], p["admin_status"],
                       p["oper_status"], p["ext_id"]))
            port_new += 1
            continue
        sets, args = [], []
        for field in ("idx", "medium", "speed_mbps", "description", "admin_status", "oper_status"):
            val = p[field]
            if val not in (None, "") and val != ex[field]:
                sets.append(f"{field} = ?"); args.append(val)
        if sets:
            c.execute(f"UPDATE ports SET {', '.join(sets)} WHERE id = ?", (*args, ex["id"]))
            port_upd += 1
    if port_new or port_upd:
        changes.append(f"Ports: {port_new} neu, {port_upd} geändert")
        if outcome == "unchanged":
            outcome = "updated"
    return outcome, changes


def run(records: list[dict], source: str, actor: str = "", dry_run: bool = False, atomic: bool = True,
        create_locations: bool = True) -> dict:
    """Wendet Geräte-Datensätze an. Rückgabe: {run_id, dry_run, applied, stats, items}."""
    started = time.time()
    items: list[dict] = []
    stats = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0}
    normalized: list[tuple[int, Optional[dict], Optional[str]]] = []
    seen_hosts: set = set()
    for i, rec in enumerate(records, 1):
        try:
            n = normalize_device(rec)
            if n["hostname"].lower() in seen_hosts:
                raise ValueError(f"{n['hostname']}: Hostname kommt mehrfach in der Quelle vor")
            seen_hosts.add(n["hostname"].lower())
            normalized.append((i, n, None))
        except ValueError as e:
            normalized.append((i, None, str(e)))

    applied = False
    with db._lock:
        try:
            with db.conn() as c:
                c.execute("BEGIN")             # explizite Transaktion: RELEASE eines Savepoints darf nichts festschreiben
                for i, n, err in normalized:
                    if err or n is None:
                        stats["errors"] += 1
                        items.append({"row": i, "hostname": str(records[i - 1].get("hostname", "")), "outcome": "error", "message": err})
                        continue
                    try:
                        c.execute("SAVEPOINT rec")
                        outcome, changes = _apply_one(c, n, source, create_locations, started)
                        c.execute("RELEASE rec")
                        stats[outcome] += 1
                        items.append({"row": i, "hostname": n["hostname"], "outcome": outcome, "changes": changes})
                    except (ValueError, sqlite3.IntegrityError) as e:
                        c.execute("ROLLBACK TO rec"); c.execute("RELEASE rec")
                        stats["errors"] += 1
                        items.append({"row": i, "hostname": n["hostname"], "outcome": "error", "message": str(e)})
                if dry_run or (atomic and stats["errors"]):
                    raise _Rollback()
                applied = True
        except _Rollback:
            applied = False

    log = "\n".join(f"#{it['row']} {it['hostname']}: {it['outcome']}" + (f" – {it.get('message')}" if it.get("message") else "")
                    for it in items[:200])
    import json as _json
    run_id = db.execute("INSERT INTO import_runs(source, started_at, finished_at, dry_run, actor, stats, log) VALUES (?,?,?,?,?,?,?)",
                        (source, started, time.time(), 1 if dry_run else 0, actor, _json.dumps({**stats, "applied": applied}), log))
    return {"run_id": run_id, "dry_run": dry_run, "applied": applied, "atomic": atomic, "stats": stats,
            "items": items[:MAX_ITEMS_IN_RESULT], "truncated": len(items) > MAX_ITEMS_IN_RESULT}
