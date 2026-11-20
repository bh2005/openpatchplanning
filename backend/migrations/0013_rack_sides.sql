-- Racks haben Vorder- und Rückseite; Geräte werden vorne, hinten oder durchgehend (beide Seiten) montiert.
-- Hochkant (vertikal) eingebaute Geräte (z. B. PDU, senkrechte Kabelführung) sitzen in einem Seitenkanal links/rechts und belegen keine 19-Zoll-HE.
ALTER TABLE devices ADD COLUMN mount_side  TEXT NOT NULL DEFAULT 'both';        -- front | rear | both (bestehende Geräte: durchgehend)
ALTER TABLE devices ADD COLUMN orientation TEXT NOT NULL DEFAULT 'horizontal';  -- horizontal (19 Zoll, HE) | vertical (Hochkant, Seitenkanal)
ALTER TABLE devices ADD COLUMN side_slot   TEXT NOT NULL DEFAULT '';            -- bei vertical: left | right (aus Sicht der jeweiligen Ansicht)
ALTER TABLE device_models ADD COLUMN mount_side  TEXT NOT NULL DEFAULT 'both';
ALTER TABLE device_models ADD COLUMN orientation TEXT NOT NULL DEFAULT 'horizontal';
ALTER TABLE device_models ADD COLUMN side_slot   TEXT NOT NULL DEFAULT '';
