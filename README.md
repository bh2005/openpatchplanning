# OpenPatchPlanning

Verwaltung und Planung von **Verkabelung/Patchungen** (Switchport ↔ Patchfeld ↔ Dose ↔ Endgerät) im Browser.
Schlank (ein Container: FastAPI + SQLite, Vue 3 / TypeScript), deutsche Oberfläche.

**Schwerpunkt ist der Ablauf, nicht die Bestandsliste:** Patchauftrag planen → freigeben → ausführen → bestätigen, mit Historie.
Per **Soll/Ist-Abgleich** (LLDP) wird geprüft, ob die dokumentierte Verbindung wirklich so steckt. Eine feste Schnittstelle zu
[OpenPlan](https://github.com/bh2005/openplan) verbindet Patchaufträge mit der Projektplanung.

> **Status: Etappe 1 (Backend).** Stammdaten-API, Benutzer/Rollen, API-Zugänge, Audit und der Import (CSV, JSON, API, Checkmk) sind
> implementiert und getestet (49 Tests). Die Oberfläche, Patchaufträge und die OpenPlan-Anbindung folgen – siehe
> [docs/konzept.md](docs/konzept.md) (Datenmodell, Ablauf, Etappen) und [docs/checkmk-import.md](docs/checkmk-import.md).

## Schnellstart (Entwicklung)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate        # Python 3.12
pip install -r requirements-dev.txt
python -m pytest -q                                   # Tests
OPP_ADMIN_PASSWORD=ChangeMe-123 uvicorn app.main:app --reload    # API und Swagger unter http://localhost:8000/api/docs
```

Konfiguration über Umgebungsvariablen (Präfix `OPP_`): `OPP_DATA_DIR` (SQLite, Standard `./data`), `OPP_ADMIN_USERNAME`,
`OPP_ADMIN_PASSWORD` (Start-Admin, nur beim ersten Start; leer = Zufallspasswort im Log), `OPP_SESSION_TTL_HOURS`.

## Geplante Funktionen

- **Import** von Geräten und Ports aus **Checkmk** (Inventar, per Skript), **CSV** (mit Spaltenzuordnung), **JSON** und per **API** (Trockenlauf, atomar, idempotent) ✔
- **Patchaufträge** mit Konfliktprüfung, Freigabe, Arbeitsanweisung (Druck/CSV/PDF) und Historie
- **Soll/Ist-Abgleich** über LLDP-Nachbarn
- **OpenPlan-Schnittstelle:** Aufträge ↔ Vorgänge, Statusrückmeldung, Webhooks
- Benutzer und Rollen (lokal, optional AD/LDAP), Audit-Log, Hilfe-Panel (`F1`), Dark Mode

## Lizenz

MIT – siehe [LICENSE](LICENSE).
