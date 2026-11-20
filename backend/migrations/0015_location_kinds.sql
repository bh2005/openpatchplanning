-- Weitere Location-Arten: Wandgehäuse (wallrack), Schaltschrank (cabinet), Anlage/Maschine (machine), mobile Maschine (vehicle, z. B. Lader).
-- Wandgehäuse und Schaltschränke können wie Racks eine HE-Teilung haben (rack_units); die Art selbst steht in locations.kind.
-- ident: Anlagen-/Maschinennummer, Kennzeichen, Fahrzeug- oder Schrankbezeichnung.
ALTER TABLE locations ADD COLUMN ident TEXT NOT NULL DEFAULT '';
