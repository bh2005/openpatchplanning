"""Einbaulage im Rack: Vorder-/Rückseite, 19-Zoll (HE) oder hochkant im Seitenkanal – und die daraus folgende Kollisionsprüfung."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from . import db
from .schemas import MOUNT_SIDES, ORIENTATIONS, SIDE_SLOTS

DEFAULT_RACK_UNITS = 42
SIDE_LABEL = {"front": "Vorderseite", "rear": "Rückseite", "both": "beide Seiten"}
SLOT_LABEL = {"left": "links", "right": "rechts"}


def check_mount(orientation: str, mount_side: str, side_slot: str) -> str:
    """Prüft die Einbaulage und liefert den bereinigten ``side_slot`` (bei 19-Zoll-Einbau immer leer)."""
    if orientation not in ORIENTATIONS:
        raise HTTPException(400, f"Ausrichtung '{orientation}' ist ungültig (erlaubt: {', '.join(ORIENTATIONS)})")
    if mount_side not in MOUNT_SIDES:
        raise HTTPException(400, f"Einbauseite '{mount_side}' ist ungültig (erlaubt: {', '.join(MOUNT_SIDES)})")
    if side_slot not in SIDE_SLOTS:
        raise HTTPException(400, f"Seitenkanal '{side_slot}' ist ungültig (erlaubt: links/rechts)")
    if orientation in ("horizontal", "din_rail"):
        return ""
    if side_slot not in ("left", "right"):
        raise HTTPException(400, "Hochkant eingebaute Geräte brauchen einen Seitenkanal (links oder rechts)")
    if mount_side == "both":
        raise HTTPException(400, "Hochkant eingebaute Geräte sitzen vorne oder hinten, nicht auf beiden Seiten")
    return side_slot


def sides(mount_side: str) -> set:
    return {"front", "rear"} if mount_side == "both" else {mount_side}


def pending_removal_device_ids() -> set:
    """Geräte, deren Rückbau in einem offenen Patchauftrag geplant ist (ihre Position darf schon neu verplant werden)."""
    return {r["device_id"] for r in db.rows(
        """SELECT DISTINCT i.device_id FROM workitems i JOIN workorders w ON w.id = i.workorder_id
           WHERE i.action = 'remove_device' AND i.device_id IS NOT NULL
             AND w.status IN ('draft', 'submitted', 'approved', 'in_progress', 'done', 'rework')""")}


def span(position: Optional[int], height: int, units: int, vertical: bool) -> Optional[tuple]:
    """Belegter HE-Bereich; hochkant eingebaute Geräte ohne Position belegen den Seitenkanal in voller Höhe."""
    if position:
        return (position, position + height - 1)
    return (1, units) if vertical else None


def rack_conflicts(loc: dict, orientation: str, mount_side: str, side_slot: str, position: Optional[int], height: int,
                   own_id: Optional[int] = None, ignore_ids=()) -> list[dict]:
    """Geräte im Rack, die mit dieser Einbaulage kollidieren.

    * 19-Zoll-Geräte kollidieren, wenn sich HE **und** Einbauseite überschneiden (ein Gerät nur vorne und eines nur hinten dürfen sich die HE teilen).
    * Hochkant-Geräte kollidieren nur mit Hochkant-Geräten im selben Seitenkanal (gleiche Seite, gleicher Kanal, überschneidende HE)."""
    if orientation == "din_rail":                         # Hutschiene/Montageplatte: kein HE-Raster, keine Kollision
        return []
    units = loc["rack_units"] or DEFAULT_RACK_UNITS
    vertical = orientation == "vertical"
    mine = span(position, height, units, vertical)
    if mine is None:
        return []
    skip = set(ignore_ids) | pending_removal_device_ids()
    out = []
    for o in db.rows("""SELECT id, hostname, type, rack_position, height_u, orientation, mount_side, side_slot
                        FROM devices WHERE location_id = ?""", (loc["id"],)):
        if o["id"] == own_id or o["id"] in skip or o["orientation"] != orientation:
            continue
        if not (sides(o["mount_side"]) & sides(mount_side)):
            continue
        if vertical and o["side_slot"] != side_slot:
            continue
        theirs = span(o["rack_position"], o["height_u"], units, vertical)
        if theirs is None or mine[1] < theirs[0] or theirs[1] < mine[0]:
            continue
        out.append(o)
    return out


def describe(o: dict) -> str:
    """Lesbare Belegung eines Geräts für Meldungen."""
    if o["orientation"] == "vertical":
        return f"{o['hostname']} ({SIDE_LABEL.get(o['mount_side'], '')} {SLOT_LABEL.get(o['side_slot'], '')} hochkant)"
    top = (o["rack_position"] or 0) + o["height_u"] - 1
    return f"{o['hostname']} (HE {o['rack_position']}–{top}, {SIDE_LABEL.get(o['mount_side'], '')})"
