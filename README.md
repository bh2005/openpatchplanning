# OpenPatchPlanning

Verwaltung und Planung von **Verkabelung/Patchungen** (Switchport ↔ Patchfeld ↔ Dose ↔ Endgerät) im Browser.
Schlank (ein Container: FastAPI + SQLite, Vue 3 / TypeScript), deutsche Oberfläche.

**Schwerpunkt ist der Ablauf, nicht die Bestandsliste:** Patchauftrag planen → freigeben → ausführen → bestätigen, mit Historie.
Per **Soll/Ist-Abgleich** (LLDP) wird geprüft, ob die dokumentierte Verbindung wirklich so steckt. Eine feste Schnittstelle zu
[OpenPlan](https://github.com/bh2005/openplan) verbindet Patchaufträge mit der Projektplanung.

> **Status: Konzeptphase.** Es gibt noch keinen Code – siehe [docs/konzept.md](docs/konzept.md) (Datenmodell, Ablauf, Import,
> OpenPlan-Schnittstelle, Etappen).

## Geplante Funktionen

- **Import** von Geräten und Ports aus **Checkmk** (REST-API/Inventar), **CSV**, **JSON** und per **API** (Trockenlauf, Vorschau, idempotent)
- **Patchaufträge** mit Konfliktprüfung, Freigabe, Arbeitsanweisung (Druck/CSV/PDF) und Historie
- **Soll/Ist-Abgleich** über LLDP-Nachbarn
- **OpenPlan-Schnittstelle:** Aufträge ↔ Vorgänge, Statusrückmeldung, Webhooks
- Benutzer und Rollen (lokal, optional AD/LDAP), Audit-Log, Hilfe-Panel (`F1`), Dark Mode

## Lizenz

MIT – siehe [LICENSE](LICENSE).
