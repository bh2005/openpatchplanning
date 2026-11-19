"""Import-Schnittstellen: CSV (mit Spaltenzuordnung), JSON und API. Alle Wege nutzen app.importer."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import audit, db, importer
from ..auth import Principal, current_principal, require_master_write

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_UPLOAD = 10 * 1024 * 1024


class JsonImport(BaseModel):
    """{"devices": [{"hostname": "sw-01", "type": "switch", "ports": [{"name": "Gi1/0/1"}]}], "dry_run": true}"""
    devices: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    dry_run: bool = False
    atomic: bool = True
    create_locations: bool = True
    source: Optional[str] = None            # ohne Angabe: "api" für API-Zugänge, "json" für Benutzer


def _source(p: Principal, explicit: Optional[str]) -> str:
    if explicit:
        if explicit not in ("json", "api", "checkmk", "openplan"):
            raise HTTPException(400, "source muss json, api, checkmk oder openplan sein")
        return explicit
    return "api" if p.kind == "token" else "json"


@router.get("/fields")
def fields(_: Principal = Depends(current_principal)):
    """Felder für die Spaltenzuordnung und das JSON-Format (für die Oberfläche und die Dokumentation)."""
    return {"devices": importer.DEVICE_FIELDS, "ports": importer.PORT_FIELDS, "required": importer.REQUIRED,
            "json_example": {"devices": [{"hostname": "sw-01", "type": "switch", "vendor": "Beispiel", "model": "X-48",
                                          "mgmt_ip": "192.0.2.10", "location": "SITE-A/Gebäude 1/Raum 2/Rack 3", "status": "active",
                                          "ext_id": "asset-1001", "ports": [{"name": "Gi1/0/1", "medium": "RJ45", "speed_mbps": 1000,
                                                                              "description": "Uplink"}]}]}}


@router.post("/csv/preview")
async def csv_preview(file: UploadFile = File(...), kind: str = Form("devices"), delimiter: str = Form(""),
                      _: Principal = Depends(require_master_write)):
    """Liest die Kopfzeile, schlägt eine Spaltenzuordnung vor und zeigt die ersten Zeilen."""
    if kind not in ("devices", "ports"):
        raise HTTPException(400, "kind muss devices oder ports sein")
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Datei zu groß (höchstens 10 MB)")
    headers, rows = importer.parse_csv(raw, delimiter)
    if not headers:
        raise HTTPException(400, "Die Datei enthält keine Daten")
    return {"headers": headers, "suggested_mapping": importer.suggest_mapping(headers, kind), "rows": len(rows),
            "sample": rows[:10], "fields": importer.DEVICE_FIELDS if kind == "devices" else importer.PORT_FIELDS,
            "required": importer.REQUIRED[kind]}


@router.post("/csv")
async def csv_import(file: UploadFile = File(...), kind: str = Form("devices"), mapping: str = Form(""),
                     delimiter: str = Form(""), dry_run: bool = Form(True), atomic: bool = Form(True),
                     create_locations: bool = Form(True), me: Principal = Depends(require_master_write)):
    """CSV importieren. Ohne mapping wird die vorgeschlagene Zuordnung verwendet. Standard: Trockenlauf."""
    if kind not in ("devices", "ports"):
        raise HTTPException(400, "kind muss devices oder ports sein")
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Datei zu groß (höchstens 10 MB)")
    try:
        m = json.loads(mapping) if mapping.strip() else None
        if m is not None and not isinstance(m, dict):
            raise ValueError("mapping muss ein JSON-Objekt {Feld: Spaltenname} sein")
        rows, used, _headers = importer.rows_from_csv(raw, kind, m, delimiter)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(400, str(e))
    if not rows:
        raise HTTPException(400, "Die Datei enthält keine Datenzeilen")
    records = importer.group_port_rows(rows) if kind == "ports" else rows
    result = importer.run(records, "csv", me.name, dry_run, atomic, create_locations)
    audit.log(me.name, "import.csv", "import", result["run_id"],
              f"{kind} {'Trockenlauf ' if dry_run else ''}{result['stats']} angewendet={result['applied']}")
    return {**result, "mapping": used}


@router.post("/json")
def json_import(body: JsonImport, me: Principal = Depends(require_master_write)):
    """Geräte (mit Ports) als JSON importieren; derselbe Weg dient der API-Anbindung (z. B. Skripte, Checkmk-Export)."""
    result = importer.run(body.devices, _source(me, body.source), me.name, body.dry_run, body.atomic, body.create_locations)
    audit.log(me.name, "import.json", "import", result["run_id"],
              f"{'Trockenlauf ' if body.dry_run else ''}{result['stats']} angewendet={result['applied']}")
    return result


@router.get("/runs")
def list_runs(limit: int = 50, _: Principal = Depends(current_principal)):
    runs = db.rows("SELECT * FROM import_runs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),))
    for r in runs:
        r["stats"] = json.loads(r["stats"] or "{}")
        r["dry_run"] = bool(r["dry_run"])
    return runs


@router.get("/runs/{rid}")
def get_run(rid: int, _: Principal = Depends(current_principal)):
    r = db.row("SELECT * FROM import_runs WHERE id = ?", (rid,))
    if not r:
        raise HTTPException(404, "Importlauf nicht gefunden")
    r["stats"] = json.loads(r["stats"] or "{}")
    r["dry_run"] = bool(r["dry_run"])
    return r
