-- Etappe 3: frei pflegbare Kabelarten und Gerätekatalog (Modelle mit Port-Vorlagen)

CREATE TABLE cable_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,       -- wird in cables.cable_type / workitems.cable_type gespeichert, unveränderlich
    category    TEXT NOT NULL DEFAULT 'other',             -- copper | fiber | power | coax | serial | telco | other
    count_label TEXT NOT NULL DEFAULT '',                  -- '' = keine Anzahl; sonst Beschriftung des Zählfelds (Fasern, Adern, Paare)
    note        TEXT NOT NULL DEFAULT '',
    builtin     INTEGER NOT NULL DEFAULT 0,                -- mitgeliefert: nicht löschbar, nur deaktivierbar
    active      INTEGER NOT NULL DEFAULT 1,
    sort        INTEGER NOT NULL DEFAULT 100
);

INSERT INTO cable_types(name, category, count_label, note, builtin, sort) VALUES
 ('Cat5e',       'copper', '',        '',                                   1, 10),
 ('Cat6',        'copper', '',        '',                                   1, 11),
 ('Cat6A',       'copper', '',        '',                                   1, 12),
 ('Cat7',        'copper', '',        '',                                   1, 13),
 ('Cat7A',       'copper', '',        '',                                   1, 14),
 ('LWL-SM-OS2',  'fiber',  'Fasern',  'Singlemode',                         1, 20),
 ('LWL-MM-OM3',  'fiber',  'Fasern',  'Multimode',                          1, 21),
 ('LWL-MM-OM4',  'fiber',  'Fasern',  'Multimode',                          1, 22),
 ('LWL-MM-OM5',  'fiber',  'Fasern',  'Multimode',                          1, 23),
 ('DAC',         'copper', '',        'Direct Attach Copper',               1, 30),
 ('AOC',         'fiber',  '',        'Active Optical Cable',               1, 31),
 ('Strom 230V',  'power',  '',        'Netzkabel (Schuko/Kaltgerät)',       1, 40),
 ('Strom C13/C14','power', '',        'Kaltgerätekabel',                    1, 41),
 ('RG58',        'coax',   '',        'Koax 50 Ohm, BNC (NTP/DCF77/Zeitsignal)', 1, 50),
 ('RG59',        'coax',   '',        'Koax 75 Ohm',                        1, 51),
 ('RS232',       'serial', 'Adern',   'Serielle Verbindung',                1, 60),
 ('RS485',       'serial', 'Adern',   'Serielle Verbindung',                1, 61),
 ('Telefon-Cu',  'telco',  'Paare',   'Kupfer-Telefonkabel (z. B. J-Y(St)Y)', 1, 70),
 ('Signal/Alarm','serial', 'Adern',   'Signal- und Alarmkontakte',          1, 71),
 ('other',       'other',  '',        'Sonstiges',                          1, 999);

CREATE TABLE device_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor      TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'switch',
    height_u    INTEGER NOT NULL DEFAULT 1,
    article_no  TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    ports       TEXT NOT NULL DEFAULT '[]',                -- JSON: Liste von Port-Gruppen {prefix, start, count, medium, speed_mbps, dual, back_suffix}
    note        TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE UNIQUE INDEX idx_device_models_name ON device_models(vendor COLLATE NOCASE, model COLLATE NOCASE);

ALTER TABLE devices ADD COLUMN model_id INTEGER REFERENCES device_models(id) ON DELETE SET NULL;
CREATE INDEX idx_devices_model ON devices(model_id);
