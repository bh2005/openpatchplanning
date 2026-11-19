-- Etappe 1: Benutzer, Audit, API-Zugänge, Standorte, Locations, Geräte, Ports, Importläufe

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    roles         TEXT NOT NULL DEFAULT 'viewer',          -- kommagetrennt: admin,planer,freigeber,techniker,viewer
    source        TEXT NOT NULL DEFAULT 'local',           -- local | ldap
    password_hash TEXT NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    last_login    REAL
);

CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    actor     TEXT NOT NULL,
    action    TEXT NOT NULL,
    entity    TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    detail    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_audit_ts ON audit_log(ts);

CREATE TABLE api_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    prefix       TEXT NOT NULL,                            -- erste Zeichen zur Anzeige
    token_hash   TEXT NOT NULL UNIQUE,                     -- SHA-256 des Tokens (Klartext wird nur einmal angezeigt)
    scope        TEXT NOT NULL DEFAULT 'read',             -- read | write
    created_by   TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL,
    expires_at   REAL,
    last_used_at REAL,
    revoked      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sites (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    code    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name    TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    note    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE locations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id    INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    parent_id  INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL DEFAULT 'room',               -- building | floor | room | rack
    name       TEXT NOT NULL,
    rack_units INTEGER,                                    -- nur bei Racks
    note       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_locations_site ON locations(site_id);
CREATE INDEX idx_locations_parent ON locations(parent_id);

CREATE TABLE devices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    type          TEXT NOT NULL DEFAULT 'switch',          -- switch | router | firewall | ap | server | patchpanel | outlet | endpoint | other
    vendor        TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    serial        TEXT NOT NULL DEFAULT '',
    mgmt_ip       TEXT NOT NULL DEFAULT '',
    location_id   INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    rack_position INTEGER,
    status        TEXT NOT NULL DEFAULT 'active',          -- planned | active | retired
    source        TEXT NOT NULL DEFAULT 'manual',          -- manual | csv | json | api | checkmk | openplan
    ext_id        TEXT NOT NULL DEFAULT '',
    last_seen     REAL,
    note          TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX idx_devices_location ON devices(location_id);
CREATE UNIQUE INDEX idx_devices_ext ON devices(source, ext_id) WHERE ext_id <> '';

CREATE TABLE ports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                              -- z. B. Gi1/0/12
    idx         INTEGER,
    medium      TEXT NOT NULL DEFAULT 'RJ45',               -- RJ45 | SFP | SFP+ | LWL | other
    speed_mbps  INTEGER,
    description TEXT NOT NULL DEFAULT '',
    admin_status TEXT NOT NULL DEFAULT '',
    oper_status  TEXT NOT NULL DEFAULT '',
    peer_port_id INTEGER REFERENCES ports(id) ON DELETE SET NULL,   -- durchgeschleift (Vorder-/Rückseite Patchfeld)
    ext_id      TEXT NOT NULL DEFAULT '',
    UNIQUE(device_id, name COLLATE NOCASE)
);
CREATE INDEX idx_ports_device ON ports(device_id);

CREATE TABLE import_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  REAL NOT NULL,
    finished_at REAL,
    dry_run     INTEGER NOT NULL DEFAULT 0,
    actor       TEXT NOT NULL DEFAULT '',
    stats       TEXT NOT NULL DEFAULT '{}',                 -- JSON: created/updated/unchanged/errors
    log         TEXT NOT NULL DEFAULT ''
);
