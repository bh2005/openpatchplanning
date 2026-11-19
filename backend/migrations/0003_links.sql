-- Geräteübergreifende Port-Verbindungen (Etappe 2)
CREATE TABLE IF NOT EXISTS links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    port_a_id  INTEGER NOT NULL UNIQUE REFERENCES ports(id) ON DELETE CASCADE,
    port_b_id  INTEGER NOT NULL UNIQUE REFERENCES ports(id) ON DELETE CASCADE,
    note       TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    CHECK (port_a_id < port_b_id)
);
CREATE INDEX IF NOT EXISTS idx_links_port_b ON links(port_b_id);
