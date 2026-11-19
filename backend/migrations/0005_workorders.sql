-- Patchaufträge (WorkOrders) und Positionen (WorkItems)
-- Bestand ändert sich über Aufträge; Direktänderungen nur für Admins (via bestehende cables-API)

CREATE TABLE IF NOT EXISTS workorders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    number      TEXT    NOT NULL UNIQUE,                    -- PA-0001
    title       TEXT    NOT NULL DEFAULT '',
    description TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'draft',           -- draft|submitted|approved|rejected|in_progress|done|confirmed|rework
    priority    TEXT    NOT NULL DEFAULT 'normal',          -- low|normal|high|critical
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    planned_from TEXT,                                      -- YYYY-MM-DD
    planned_to   TEXT,
    note        TEXT    NOT NULL DEFAULT '',
    openplan_project TEXT NOT NULL DEFAULT '',
    openplan_task    TEXT NOT NULL DEFAULT '',
    openplan_link    TEXT NOT NULL DEFAULT '',
    created_by  TEXT    NOT NULL DEFAULT '',
    created_at  REAL    NOT NULL DEFAULT 0,
    updated_at  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workitems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workorder_id    INTEGER NOT NULL REFERENCES workorders(id) ON DELETE CASCADE,
    action          TEXT    NOT NULL DEFAULT 'connect',     -- connect|disconnect|move
    port_a_id       INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    port_b_id       INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    old_port_b_id   INTEGER REFERENCES ports(id) ON DELETE SET NULL,  -- nur bei move: alter Zielport
    cable_label     TEXT    NOT NULL DEFAULT '',
    cable_type      TEXT    NOT NULL DEFAULT 'other',
    fiber_count     INTEGER,
    length_m        REAL,
    color           TEXT    NOT NULL DEFAULT '',
    note            TEXT    NOT NULL DEFAULT '',
    item_status     TEXT    NOT NULL DEFAULT 'open',        -- open|done|deviation
    deviation_note  TEXT    NOT NULL DEFAULT '',
    executed_by     TEXT    NOT NULL DEFAULT '',
    executed_at     REAL,
    idx             INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_workitems_workorder ON workitems(workorder_id);

-- Kabeln zuordnen welcher Auftrag sie erzeugt hat
ALTER TABLE cables ADD COLUMN workorder_id INTEGER REFERENCES workorders(id) ON DELETE SET NULL;
