-- Anbindung an OpenPlan (Projektplanung): Status der zuletzt abgeglichenen OpenPlan-Aufgabe je Patchauftrag.
-- openplan_project / openplan_task / openplan_link (Migration 0005) halten die Verknüpfung.
ALTER TABLE workorders ADD COLUMN openplan_status    TEXT NOT NULL DEFAULT '';
ALTER TABLE workorders ADD COLUMN openplan_percent   REAL;
ALTER TABLE workorders ADD COLUMN openplan_synced_at REAL;
ALTER TABLE workorders ADD COLUMN openplan_error     TEXT NOT NULL DEFAULT '';
