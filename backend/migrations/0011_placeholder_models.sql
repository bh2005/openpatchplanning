-- Platzhalter für Rackplatz ohne Ports: Kabelführung, Blindblende, Fachboden
INSERT INTO device_models(vendor, model, type, height_u, description, ports, created_at, updated_at) VALUES
 ('Generisch', 'Kabelführung 1 HE', 'cable_mgmt', 1, 'Generisches Kabelführungspanel (Rangierpanel mit Ringen/Bügeln), 1 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Kabelführung 2 HE', 'cable_mgmt', 2, 'Generisches Kabelführungspanel, 2 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Bürstenpanel 1 HE', 'cable_mgmt', 1, 'Generisches Bürstenpanel für Kabeldurchführung, 1 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Blindblende 1 HE', 'blank_panel', 1, 'Blindblende zum Verschließen freier Höheneinheiten, 1 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Blindblende 2 HE', 'blank_panel', 2, 'Blindblende, 2 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Blindblende 3 HE', 'blank_panel', 3, 'Blindblende, 3 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Fachboden 1 HE', 'shelf', 1, 'Fachboden/Ablage im 19-Zoll-Rack, 1 HE', '[]', strftime('%s','now'), strftime('%s','now')),
 ('Generisch', 'Fachboden 2 HE', 'shelf', 2, 'Fachboden/Ablage im 19-Zoll-Rack, 2 HE', '[]', strftime('%s','now'), strftime('%s','now'));
