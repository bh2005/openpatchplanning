-- Gerätehöhe in Höheneinheiten (HE) für die Rack-Ansicht
ALTER TABLE devices ADD COLUMN height_u INTEGER NOT NULL DEFAULT 1;
