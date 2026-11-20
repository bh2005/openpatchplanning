-- WAN-Verbindungen (Leitungsverzeichnis) und Auftragspositionen dafür
CREATE TABLE IF NOT EXISTS wan_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'planned',      -- planned|ordered|active|suspended|terminated
    technology      TEXT    NOT NULL DEFAULT 'other',        -- fiber|mpls|dsl|cable|lte|sdwan|leased|other
    site_a_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_b_id       INTEGER REFERENCES sites(id) ON DELETE SET NULL,     -- leer = Internet/Provider-Wolke
    remote_label    TEXT    NOT NULL DEFAULT '',             -- Gegenstelle als Freitext, wenn kein eigener Standort
    port_a_id       INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    port_b_id       INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    provider        TEXT    NOT NULL DEFAULT '',
    circuit_id      TEXT    NOT NULL DEFAULT '',
    bandwidth_down  REAL,                                    -- Mbit/s
    bandwidth_up    REAL,
    contract_number TEXT    NOT NULL DEFAULT '',
    contract_start  TEXT,                                    -- YYYY-MM-DD
    contract_end    TEXT,
    notice_days     INTEGER,
    monthly_cost    REAL,
    contact         TEXT    NOT NULL DEFAULT '',
    note            TEXT    NOT NULL DEFAULT '',
    activated_at    REAL,
    terminated_at   REAL,
    created_by      TEXT    NOT NULL DEFAULT '',
    created_at      REAL    NOT NULL DEFAULT 0,
    updated_at      REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wan_site_a ON wan_links(site_a_id);
CREATE INDEX IF NOT EXISTS idx_wan_site_b ON wan_links(site_b_id);

ALTER TABLE workitems ADD COLUMN wan_link_id INTEGER REFERENCES wan_links(id) ON DELETE SET NULL;
ALTER TABLE workitems ADD COLUMN wan_patch   TEXT NOT NULL DEFAULT '';     -- JSON: Änderungen bei wan_change
