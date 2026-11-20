-- Zurückgebaute Geräte geben ihren Hostnamen frei (er wird umbenannt); der ursprüngliche Name bleibt in der Historie.
-- planned_hostname: Ein Ersatzgerät trägt bis zum Rückbau des alten Geräts einen vorläufigen Namen und übernimmt den Wunschnamen danach.
ALTER TABLE devices ADD COLUMN former_hostname  TEXT NOT NULL DEFAULT '';
ALTER TABLE devices ADD COLUMN planned_hostname TEXT NOT NULL DEFAULT '';
ALTER TABLE devices ADD COLUMN retired_at       REAL;
