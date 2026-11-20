-- Beobachtete Nachbarn (LLDP/CDP) für den Soll/Ist-Abgleich
CREATE TABLE IF NOT EXISTS observations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id        INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    port_id          INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    local_port       TEXT    NOT NULL DEFAULT '',
    protocol         TEXT    NOT NULL DEFAULT 'lldp',        -- lldp | cdp
    neighbor_name    TEXT    NOT NULL DEFAULT '',
    neighbor_port    TEXT    NOT NULL DEFAULT '',
    neighbor_address TEXT    NOT NULL DEFAULT '',
    capabilities     TEXT    NOT NULL DEFAULT '',
    seen_at          REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_obs_device ON observations(device_id);

-- Zeitpunkt der letzten Nachbar-Meldung (leer = für dieses Gerät liegen keine LLDP/CDP-Daten vor)
ALTER TABLE devices ADD COLUMN neighbors_at REAL;
