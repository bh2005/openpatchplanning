# Import aus Checkmk

OpenPatchPlanning liest Geräte und Ports aus dem **Checkmk-HW/SW-Inventar**. Das Inventar enthält für Netzwerkgeräte
(Checkmk-Knoten `networking.interfaces`) Interfaces mit Name, Beschreibung, Geschwindigkeit und Status, dazu Hersteller,
Modell und Seriennummer (`hardware.components.chassis`), die Management-IP und die **LLDP-Nachbarn**
(`networking.lldp_cache.neighbors`, wird für den Soll/Ist-Abgleich in Etappe 3 verwendet).

Der Import läuft über ein kleines Skript auf dem Checkmk-Server ([tools/checkmk_export.py](../tools/checkmk_export.py), nur Python 3,
keine Abhängigkeiten). So braucht OpenPatchPlanning keinen Zugriff auf Checkmk-Interna; die Umwandlung geschieht im Server und ist getestet.

## Einrichten

1. In OpenPatchPlanning (als Administrator): Verwaltung → **API-Zugänge** → neuen Zugang mit Umfang **write** anlegen. Das Token `opp_…`
   wird nur einmal angezeigt.
2. Das Skript auf den Checkmk-Server kopieren (als Site-Benutzer oder root ausführbar).

## Verwenden

```bash
export OPP_URL=https://opp.example.com
export OPP_TOKEN=opp_...            # besser als Umgebungsvariable (taucht nicht in der Prozessliste auf)

# 1. Trockenlauf: zeigt, was angelegt/geändert würde, speichert nichts
./checkmk_export.py --site mysite --dry-run

# 2. Import (alle Hosts mit Interfaces), Geräte einem Standort zuordnen
./checkmk_export.py --site mysite --site-code SITE-A

# nur bestimmte Hosts, interne CA für HTTPS
./checkmk_export.py --site mysite --hosts '^sw-' --ca-file /etc/ssl/certs/internal-ca.pem
```

| Option | Bedeutung |
|---|---|
| `--site` / `--inventory-dir` | Checkmk-Site bzw. Verzeichnis der Inventar-JSONs (Standard `/omd/sites/<site>/var/check_mk/inventory`) |
| `--hosts` | regulärer Ausdruck für Hostnamen |
| `--site-code` | Standort-Code, dem alle Geräte zugeordnet werden (Location „Allgemein“); sonst bleibt der Standort leer |
| `--all-interfaces` | auch Loopbacks, VLANs und Tunnel als Ports übernehmen (Standard: nur Ethernet-Ports) |
| `--dry-run` | nichts speichern |
| `--no-atomic` | fehlerhafte Hosts überspringen statt den ganzen Stapel abzulehnen |
| `--batch` | Hosts je Anfrage (Standard 300) |
| `--print` | nur als JSON ausgeben (z. B. zum Prüfen) |

Regelmäßig ausführen (Cron auf dem Checkmk-Server) hält den Bestand aktuell; der Import ist **idempotent**.

## Regeln

- **Schlüssel:** der Checkmk-Hostname (`ext_id`). Wird ein Host in Checkmk umbenannt, aber `ext_id` bleibt gleich, wird das Gerät umbenannt statt doppelt angelegt.
- **Nur Stammdaten:** der Import legt Geräte und Ports an und aktualisiert sie. **Bestehende Verbindungen ändert er nie** – das tun nur Patchaufträge.
- **Leere Werte** in der Quelle überschreiben nichts. Ports, die im Inventar fehlen, werden **nicht** gelöscht.
- **Gerätetyp** wird aus Modell/Produkt geraten (`switch`, `ap`, `firewall`, `router`; sonst `other`) und kann in der Oberfläche korrigiert werden.
- **Medium:** Ports ab 10 Gbit/s werden als `SFP+` geführt, alle anderen als `RJ45` (Standard). Auch das lässt sich nachträglich ändern.
- Hosts ohne Interfaces im Inventar (z. B. Server ohne Netzwerk-Inventar) werden übersprungen und im Ergebnis aufgeführt.

## Direkt per API

Das Skript ruft `POST /api/import/checkmk` auf; das lässt sich auch ohne Skript nutzen:

```json
{"hosts": [{"host": "sw-01", "inventory": { "Nodes": { "networking": { "...": "Inventarbaum wie in var/check_mk/inventory/sw-01.json" } } } }],
 "dry_run": true, "atomic": true, "site_code": "SITE-A", "include_all_interfaces": false, "all_hosts": false}
```

Swagger-Dokumentation: `/api/docs`.
