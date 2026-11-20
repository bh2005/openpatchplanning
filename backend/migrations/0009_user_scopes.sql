-- Rechte pro Standort: eine Rolle gilt nur für einen Standort (ganzer Standort samt Locations, Geräten, Kabeln, Aufträgen).
-- Globale Rollen bleiben in users.roles; ein Benutzer ohne globale Rolle sieht und ändert nur seine Standorte.
CREATE TABLE user_scopes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role     TEXT NOT NULL,                                -- admin | planer | freigeber | techniker | viewer
    site_id  INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source   TEXT NOT NULL DEFAULT 'manual',               -- manual | ldap (aus AD-Gruppen, bei jeder Anmeldung neu berechnet)
    UNIQUE(user_id, role, site_id)
);
CREATE INDEX idx_user_scopes_user ON user_scopes(user_id);
CREATE INDEX idx_user_scopes_site ON user_scopes(site_id);
