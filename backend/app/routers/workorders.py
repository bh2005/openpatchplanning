"""Patchaufträge (WorkOrders) mit Workflow und Positionen (WorkItems).

Rollen:
  planer    – Aufträge anlegen, einreichen (eigene)
  freigeber – Aufträge freigeben/ablehnen, bestätigen/zurückweisen
  techniker – Ausführung starten, Positionen abhaken
  admin     – alles; kann auch direkt Kabel über die masterdata-API setzen
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, db
from ..auth import Principal, current_principal
from ..schemas import (CABLE_TYPES, PRIORITIES, WORKITEM_ACTIONS, WORKITEM_STATUSES,
                       WORKORDER_STATUSES, WorkItemExec, WorkItemIn, WorkOrderIn)

router = APIRouter(prefix="/api/workorders", tags=["aufträge"])

# ── Status-Übergänge: {aktueller Status: {aktion: (neuer Status, erlaubte Rollen)}} ──────

TRANSITIONS: dict[str, dict[str, tuple[str, list[str]]]] = {
    "draft":       {"submit":   ("submitted",   ["planer", "admin"])},
    "submitted":   {"approve":  ("approved",    ["freigeber", "admin"]),
                    "reject":   ("rejected",    ["freigeber", "admin"])},
    "approved":    {"start":    ("in_progress", ["techniker", "admin"])},
    "in_progress": {"finish":   ("done",        ["techniker", "admin"])},
    "done":        {"confirm":  ("confirmed",   ["freigeber", "admin"]),
                    "rework":   ("rework",      ["freigeber", "admin"])},
    "rework":      {"start":    ("in_progress", ["techniker", "admin"])},
}

STATUS_LABELS = {
    "draft": "Entwurf", "submitted": "Eingereicht", "approved": "Freigegeben",
    "rejected": "Abgelehnt", "in_progress": "In Ausführung", "done": "Ausgeführt",
    "confirmed": "Bestätigt", "rework": "Nacharbeit",
}

ACTION_LABELS = {"connect": "Verbindung herstellen", "disconnect": "Verbindung trennen", "move": "Verbindung umstecken"}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _next_number() -> str:
    row = db.row("SELECT MAX(CAST(SUBSTR(number,4) AS INTEGER)) AS n FROM workorders WHERE number LIKE 'PA-%'")
    n = (row["n"] or 0) + 1
    return f"PA-{n:04d}"


def _require_role(me: Principal, roles: list[str]) -> None:
    if me.is_admin:
        return
    if not me.has(*roles):
        raise HTTPException(403, f"Fehlende Rolle (erforderlich: {', '.join(roles)})")


def _wo_or_404(wid: int) -> dict:
    w = db.row("SELECT * FROM workorders WHERE id = ?", (wid,))
    if not w:
        raise HTTPException(404, "Patchauftrag nicht gefunden")
    return w


def _item_or_404(iid: int, wid: int) -> dict:
    item = db.row("SELECT * FROM workitems WHERE id = ? AND workorder_id = ?", (iid, wid))
    if not item:
        raise HTTPException(404, "Position nicht gefunden")
    return item


def _port_info(pid: Optional[int]) -> Optional[dict]:
    if not pid:
        return None
    r = db.row(
        "SELECT p.id, p.name, p.device_id, d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?",
        (pid,)
    )
    return {"id": r["id"], "name": r["name"], "device_id": r["device_id"], "device_hostname": r["hostname"]} if r else None


def _item_out(item: dict) -> dict:
    return {
        "id":           item["id"],
        "workorder_id": item["workorder_id"],
        "action":       item["action"],
        "port_a":       _port_info(item["port_a_id"]),
        "port_b":       _port_info(item["port_b_id"]),
        "old_port_b":   _port_info(item["old_port_b_id"]),
        "cable_label":  item["cable_label"],
        "cable_type":   item["cable_type"],
        "fiber_count":  item["fiber_count"],
        "length_m":     item["length_m"],
        "color":        item["color"],
        "note":         item["note"],
        "item_status":  item["item_status"],
        "deviation_note": item["deviation_note"],
        "executed_by":  item["executed_by"],
        "executed_at":  item["executed_at"],
        "idx":          item["idx"],
    }


def _wo_out(w: dict, with_items: bool = False) -> dict:
    loc = None
    if w["location_id"]:
        loc = db.row("SELECT id, name, kind FROM locations WHERE id = ?", (w["location_id"],))
    out = {
        "id":           w["id"],
        "number":       w["number"],
        "title":        w["title"],
        "description":  w["description"],
        "status":       w["status"],
        "status_label": STATUS_LABELS.get(w["status"], w["status"]),
        "priority":     w["priority"],
        "location":     dict(loc) if loc else None,
        "planned_from": w["planned_from"],
        "planned_to":   w["planned_to"],
        "note":         w["note"],
        "openplan_project": w["openplan_project"],
        "openplan_task":    w["openplan_task"],
        "openplan_link":    w["openplan_link"],
        "created_by":   w["created_by"],
        "created_at":   w["created_at"],
        "updated_at":   w["updated_at"],
    }
    if with_items:
        out["items"] = [_item_out(i) for i in db.rows(
            "SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (w["id"],)
        )]
    return out


def _apply_workorder(w: dict, me: Principal) -> None:
    """Führt alle Positionen eines bestätigten Auftrags auf den Kabelbestand aus."""
    items = db.rows("SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (w["id"],))
    for item in items:
        if item["item_status"] == "deviation":
            continue  # Abweichungen nicht automatisch ausführen
        action = item["action"]
        a_id   = item["port_a_id"]
        b_id   = item["port_b_id"]

        if action == "connect" and a_id and b_id:
            # bestehende Verbindungen an beiden Ports entfernen
            db.execute("DELETE FROM cables WHERE port_a_id IN (?,?) OR port_b_id IN (?,?)", (a_id, b_id, a_id, b_id))
            lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            db.execute(
                """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m,
                                      color, installed_at, measurement_ref, measurement_ok, note,
                                      created_by, created_at, workorder_id)
                   VALUES (?,?,?,?,?,?,?,NULL,'',NULL,?,?,?,?)""",
                (lo, hi, item["cable_label"], item["cable_type"], item["fiber_count"], item["length_m"],
                 item["color"], item["note"], me.name, time.time(), w["id"]),
            )

        elif action == "disconnect" and a_id:
            db.execute("DELETE FROM cables WHERE port_a_id = ? OR port_b_id = ?", (a_id, a_id))
            if b_id:
                db.execute("DELETE FROM cables WHERE port_a_id = ? OR port_b_id = ?", (b_id, b_id))

        elif action == "move" and a_id and b_id:
            # alten Zielport lösen, neuen verbinden
            old_b = item["old_port_b_id"]
            if old_b:
                db.execute("DELETE FROM cables WHERE port_a_id IN (?,?) OR port_b_id IN (?,?)", (a_id, old_b, a_id, old_b))
            else:
                db.execute("DELETE FROM cables WHERE port_a_id = ? OR port_b_id = ?", (a_id, a_id))
            db.execute("DELETE FROM cables WHERE port_a_id = ? OR port_b_id = ?", (b_id, b_id))
            lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            db.execute(
                """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m,
                                      color, installed_at, measurement_ref, measurement_ok, note,
                                      created_by, created_at, workorder_id)
                   VALUES (?,?,?,?,?,?,?,NULL,'',NULL,?,?,?,?)""",
                (lo, hi, item["cable_label"], item["cable_type"], item["fiber_count"], item["length_m"],
                 item["color"], item["note"], me.name, time.time(), w["id"]),
            )


# ── CRUD Aufträge ─────────────────────────────────────────────────────────────

@router.get("")
def list_workorders(
    status: Optional[str] = None,
    q: Optional[str] = None,
    _: Principal = Depends(current_principal),
):
    where, args = [], []
    if status and status in WORKORDER_STATUSES:
        where.append("status = ?"); args.append(status)
    if q:
        where.append("(number LIKE ? OR title LIKE ? OR created_by LIKE ?)"); args += [f"%{q}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.rows(f"SELECT * FROM workorders {w} ORDER BY id DESC", tuple(args))
    return [_wo_out(r) for r in rows]


@router.post("", status_code=201)
def create_workorder(body: WorkOrderIn, me: Principal = Depends(current_principal)):
    _require_role(me, ["planer", "admin"])
    if body.priority not in PRIORITIES:
        raise HTTPException(400, f"Ungültige Priorität: {body.priority}")
    now = time.time()
    wid = db.execute(
        """INSERT INTO workorders(number, title, description, status, priority, location_id,
                                  planned_from, planned_to, note, openplan_project, openplan_task, openplan_link,
                                  created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_next_number(), body.title.strip(), body.description.strip(), "draft", body.priority,
         body.location_id, body.planned_from, body.planned_to, body.note.strip(),
         body.openplan_project.strip(), body.openplan_task.strip(), body.openplan_link.strip(),
         me.name, now, now),
    )
    audit.log(me.name, "workorder.create", "workorder", wid, body.title)
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


@router.get("/{wid}")
def get_workorder(wid: int, _: Principal = Depends(current_principal)):
    return _wo_out(_wo_or_404(wid), with_items=True)


@router.put("/{wid}")
def update_workorder(wid: int, body: WorkOrderIn, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Nur Entwürfe und zurückgewiesene Aufträge können bearbeitet werden")
    _require_role(me, ["planer", "admin"])
    if body.priority not in PRIORITIES:
        raise HTTPException(400, f"Ungültige Priorität: {body.priority}")
    db.execute(
        """UPDATE workorders SET title=?, description=?, priority=?, location_id=?, planned_from=?, planned_to=?,
                                 note=?, openplan_project=?, openplan_task=?, openplan_link=?, updated_at=?
           WHERE id=?""",
        (body.title.strip(), body.description.strip(), body.priority, body.location_id,
         body.planned_from, body.planned_to, body.note.strip(),
         body.openplan_project.strip(), body.openplan_task.strip(), body.openplan_link.strip(),
         time.time(), wid),
    )
    audit.log(me.name, "workorder.update", "workorder", wid, body.title)
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


@router.delete("/{wid}")
def delete_workorder(wid: int, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid)
    if w["status"] not in ("draft", "rejected"):
        raise HTTPException(409, "Nur Entwürfe oder abgelehnte Aufträge können gelöscht werden")
    _require_role(me, ["planer", "admin"])
    db.execute("DELETE FROM workorders WHERE id = ?", (wid,))
    audit.log(me.name, "workorder.delete", "workorder", wid, w["number"])
    return {"ok": True}


# ── Status-Übergänge ─────────────────────────────────────────────────────────

@router.post("/{wid}/transition/{action}")
def transition(wid: int, action: str, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid)
    trans = TRANSITIONS.get(w["status"], {})
    if action not in trans:
        raise HTTPException(409,
            f"Aktion '{action}' nicht möglich bei Status '{STATUS_LABELS.get(w['status'], w['status'])}' "
            f"(möglich: {', '.join(trans.keys()) or '–'})")
    new_status, roles = trans[action]
    _require_role(me, roles)

    if action == "confirm":
        _apply_workorder(w, me)
        audit.log(me.name, "workorder.confirm", "workorder", wid, w["number"])

    db.execute("UPDATE workorders SET status = ?, updated_at = ? WHERE id = ?", (new_status, time.time(), wid))
    audit.log(me.name, f"workorder.{action}", "workorder", wid, w["number"])
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


# ── Positionen (WorkItems) ────────────────────────────────────────────────────

@router.get("/{wid}/items")
def list_items(wid: int, _: Principal = Depends(current_principal)):
    _wo_or_404(wid)
    return [_item_out(i) for i in db.rows(
        "SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (wid,)
    )]


@router.post("/{wid}/items", status_code=201)
def add_item(wid: int, body: WorkItemIn, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
    _require_role(me, ["planer", "admin"])
    if body.action not in WORKITEM_ACTIONS:
        raise HTTPException(400, f"Ungültige Aktion: {body.action}")
    if body.cable_type not in CABLE_TYPES:
        raise HTTPException(400, f"Ungültiger Kabeltyp: {body.cable_type}")
    iid = db.execute(
        """INSERT INTO workitems(workorder_id, action, port_a_id, port_b_id, old_port_b_id,
                                  cable_label, cable_type, fiber_count, length_m, color, note, idx)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (wid, body.action, body.port_a_id, body.port_b_id, body.old_port_b_id,
         body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
         body.color.strip(), body.note.strip(), body.idx),
    )
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, "workitem.add", "workorder", wid, f"item {iid}")
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))


@router.put("/{wid}/items/{iid}")
def update_item(wid: int, iid: int, body: WorkItemIn, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen bearbeitet werden")
    _require_role(me, ["planer", "admin"])
    _item_or_404(iid, wid)
    if body.action not in WORKITEM_ACTIONS:
        raise HTTPException(400, f"Ungültige Aktion: {body.action}")
    if body.cable_type not in CABLE_TYPES:
        raise HTTPException(400, f"Ungültiger Kabeltyp: {body.cable_type}")
    db.execute(
        """UPDATE workitems SET action=?, port_a_id=?, port_b_id=?, old_port_b_id=?,
                                cable_label=?, cable_type=?, fiber_count=?, length_m=?,
                                color=?, note=?, idx=? WHERE id=?""",
        (body.action, body.port_a_id, body.port_b_id, body.old_port_b_id,
         body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
         body.color.strip(), body.note.strip(), body.idx, iid),
    )
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, "workitem.update", "workorder", wid, f"item {iid}")
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))


@router.delete("/{wid}/items/{iid}")
def delete_item(wid: int, iid: int, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen gelöscht werden")
    _require_role(me, ["planer", "admin"])
    _item_or_404(iid, wid)
    db.execute("DELETE FROM workitems WHERE id = ?", (iid,))
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, "workitem.delete", "workorder", wid, f"item {iid}")
    return {"ok": True}


@router.post("/{wid}/items/{iid}/execute")
def execute_item(wid: int, iid: int, body: WorkItemExec, me: Principal = Depends(current_principal)):
    """Techniker hakt eine Position ab (erledigt oder Abweichung)."""
    w = _wo_or_404(wid)
    if w["status"] != "in_progress":
        raise HTTPException(409, "Positionen können nur bei Status 'In Ausführung' abgehakt werden")
    _require_role(me, ["techniker", "admin"])
    item = _item_or_404(iid, wid)
    if body.item_status not in ("done", "deviation"):
        raise HTTPException(400, "item_status muss 'done' oder 'deviation' sein")
    db.execute(
        """UPDATE workitems SET item_status=?, deviation_note=?, executed_by=?, executed_at=? WHERE id=?""",
        (body.item_status, body.deviation_note.strip(), me.name, time.time(), iid),
    )
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, f"workitem.{body.item_status}", "workorder", wid, f"item {iid}")
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))


@router.post("/{wid}/items/{iid}/reopen")
def reopen_item(wid: int, iid: int, me: Principal = Depends(current_principal)):
    """Abhakung einer Position rückgängig machen (nur in in_progress)."""
    w = _wo_or_404(wid)
    if w["status"] != "in_progress":
        raise HTTPException(409, "Nur bei Status 'In Ausführung' möglich")
    _require_role(me, ["techniker", "admin"])
    _item_or_404(iid, wid)
    db.execute("UPDATE workitems SET item_status='open', deviation_note='', executed_by='', executed_at=NULL WHERE id=?", (iid,))
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))
