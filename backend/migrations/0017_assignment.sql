-- Patchaufträge können einem Benutzer zugewiesen werden (Verantwortlicher/Ausführender); „Meine Aufgaben“ zeigt sie auf der Startseite.
ALTER TABLE workorders ADD COLUMN assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE workorders ADD COLUMN assigned_at REAL;
