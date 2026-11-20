-- Blindblenden und Kabelführungen (19 Zoll) sind einseitig montiert: eine Blindblende vorne darf die Rückseite derselben HE nicht blockieren
-- (dort kann z. B. eine Kabelführung sitzen). Fachböden bleiben durchgehend.
UPDATE device_models SET mount_side = 'front' WHERE type IN ('blank_panel', 'cable_mgmt') AND orientation = 'horizontal' AND mount_side = 'both';
UPDATE devices       SET mount_side = 'front' WHERE type IN ('blank_panel', 'cable_mgmt') AND orientation = 'horizontal' AND mount_side = 'both';
