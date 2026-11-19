-- Kabelmanagement: links-Tabelle zu cables erweitern
ALTER TABLE links RENAME TO cables;
ALTER TABLE cables ADD COLUMN cable_label   TEXT NOT NULL DEFAULT '';
ALTER TABLE cables ADD COLUMN cable_type    TEXT NOT NULL DEFAULT 'other';
ALTER TABLE cables ADD COLUMN fiber_count   INTEGER;
ALTER TABLE cables ADD COLUMN length_m      REAL;
ALTER TABLE cables ADD COLUMN color         TEXT NOT NULL DEFAULT '';
ALTER TABLE cables ADD COLUMN installed_at  TEXT;
ALTER TABLE cables ADD COLUMN measurement_ref  TEXT NOT NULL DEFAULT '';
ALTER TABLE cables ADD COLUMN measurement_ok   INTEGER;
DROP INDEX IF EXISTS idx_links_port_b;
CREATE INDEX IF NOT EXISTS idx_cables_port_b ON cables(port_b_id);
