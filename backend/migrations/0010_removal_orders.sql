-- Geräte in Patchaufträgen (Einbau/Rückbau) und Abhängigkeit zwischen Aufträgen (Rückbau vor Einbau)
ALTER TABLE workitems ADD COLUMN device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL;
ALTER TABLE workorders ADD COLUMN depends_on INTEGER REFERENCES workorders(id) ON DELETE SET NULL;
