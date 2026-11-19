"""Kennzahlen für die Übersichtsseite."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from .. import db
from ..auth import Principal, current_principal

router = APIRouter(prefix="/api", tags=["übersicht"])


def _count_by(column: str) -> dict:
    return {r[column]: r["n"] for r in db.rows(f"SELECT {column}, COUNT(*) AS n FROM devices GROUP BY {column}")}


@router.get("/stats")
def stats(_: Principal = Depends(current_principal)):
    runs = db.rows("SELECT * FROM import_runs ORDER BY id DESC LIMIT 5")
    for r in runs:
        r["stats"] = json.loads(r["stats"] or "{}")
        r["dry_run"] = bool(r["dry_run"])
    return {
        "sites": db.row("SELECT COUNT(*) AS n FROM sites")["n"],
        "locations": db.row("SELECT COUNT(*) AS n FROM locations")["n"],
        "racks": db.row("SELECT COUNT(*) AS n FROM locations WHERE kind = 'rack'")["n"],
        "devices": db.row("SELECT COUNT(*) AS n FROM devices")["n"],
        "ports": db.row("SELECT COUNT(*) AS n FROM ports")["n"],
        "devices_without_location": db.row("SELECT COUNT(*) AS n FROM devices WHERE location_id IS NULL")["n"],
        "devices_by_type": _count_by("type"),
        "devices_by_status": _count_by("status"),
        "devices_by_source": _count_by("source"),
        "last_imports": runs,
    }
