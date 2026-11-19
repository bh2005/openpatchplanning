// Handbuch: Abschnitte mit Überschrift und HTML-Inhalt (Seite /handbuch).
export const sections = [
  { id: 'einstieg', title: 'Einstieg', html: `
<p>OpenPatchPlanning verwaltet den Bestand für die Verkabelung: Standorte, Räume und Racks, Geräte mit Ports sowie Patchfelder und Dosen. Der Schwerpunkt liegt auf der <b>Planung</b>: Änderungen an der Verkabelung laufen später als Auftrag (planen → freigeben → ausführen → bestätigen).</p>
<p>In dieser Ausbaustufe stehen die Stammdaten und der Import zur Verfügung.</p>
<h3>Typischer Start</h3>
<ol><li>Unter <b>Standorte</b> Standorte, Gebäude, Räume und Racks anlegen – oder beim Import anlegen lassen.</li>
<li>Unter <b>Import</b> Geräte und Ports aus CSV, JSON oder Checkmk einlesen.</li>
<li>Unter <b>Racks</b> die Belegung prüfen, unter <b>Geräte</b> Details und Ports pflegen.</li></ol>` },

  { id: 'bedienung', title: 'Bedienung', html: `
<ul><li><b>Hilfe:</b> F1 oder ? öffnet die Hilfe zur aktuellen Seite. Das Fragezeichen-Symbol neben Feldern zeigt einen Kurztipp.</li>
<li><b>Dunkelmodus</b> und <b>Profil</b> (Passwort ändern) findest du unten in der Seitenleiste.</li>
<li>Die Seitenleiste lässt sich über das Menü-Symbol einklappen.</li></ul>` },

  { id: 'standorte', title: 'Standorte und Racks', html: `
<p>Die Struktur ist hierarchisch: <b>Standort → Gebäude → Etage → Raum → Rack</b>. Jede Ebene ist eine „Location“. Racks haben eine Höhe in Höheneinheiten (HE).</p>
<p>Standorte und Locations lassen sich nur löschen, wenn sie leer sind. Beim Import reicht ein Pfad wie <code>SITE-A/Gebäude 1/Raum 2/Rack 3</code>; fehlende Ebenen werden angelegt. Wird nur ein Standortcode angegeben, landet das Gerät in der Location „Allgemein“.</p>` },

  { id: 'geraete', title: 'Geräte und Ports', html: `
<p>Gerätetypen: Switch, Router, Firewall, Access Point, Server, Patchfeld, Dose, Endgerät, Sonstiges. Der Status ist <i>geplant</i>, <i>aktiv</i> oder <i>außer Betrieb</i>.</p>
<ul><li><b>HE-Position und Höhe</b> sind nur in einem Rack möglich. Überschneidungen und Überschreiten der Rackhöhe werden abgewiesen.</li>
<li><b>Ports</b> lassen sich einzeln oder gesammelt anlegen (Präfix, Start, Anzahl).</li>
<li><b>Patchfelder:</b> jeder Port kann mit einer Gegenseite verknüpft werden (Durchschleifung).</li></ul>` },

  { id: 'import', title: 'Import', html: `
<p>Der Import legt Geräte und Ports an und aktualisiert sie. Er ändert nie Verbindungen.</p>
<h3>Regeln</h3>
<ul><li><b>Wiedererkennung:</b> über Quell-ID, sonst über den Hostnamen (Groß-/Kleinschreibung egal). Wiederholte Importe erzeugen keine Dubletten.</li>
<li><b>Leere Felder</b> überschreiben vorhandene Werte nicht. <b>Fehlende Ports</b> werden nicht gelöscht.</li>
<li><b>Trockenlauf</b> zeigt das Ergebnis, ohne zu speichern. <b>Atomar</b> speichert bei einem Fehler nichts.</li></ul>
<h3>CSV</h3>
<p>Datei wählen, Spalten zuordnen (wird vorgeschlagen), Trockenlauf, Import. Geräte-Felder: hostname, type, vendor, model, serial, mgmt_ip, location, status, note, ext_id. Port-Felder: hostname, port, idx, medium, speed_mbps, description, admin_status, oper_status.</p>
<h3>JSON und API</h3>
<p>Das JSON-Format ist identisch zur API <code>POST /api/import/json</code>. Ein Beispiel fügt die Schaltfläche „Beispiel einfügen“ ein.</p>
<h3>Checkmk</h3>
<p>Das Skript <code>tools/checkmk_export.py</code> liest das HW/SW-Inventar und sendet es an <code>POST /api/import/checkmk</code>. Es braucht einen API-Zugang mit Schreibrecht. Ethernet-Schnittstellen werden zu Ports, ab 10 Gbit/s mit Medium SFP+. Loopbacks, VLAN-Schnittstellen und Tunnel werden nicht übernommen.</p>` },

  { id: 'verwaltung', title: 'Verwaltung', html: `
<h3>Rollen</h3>
<table><tr><th>Rolle</th><th>Darf</th></tr>
<tr><td>Administrator</td><td>alles, inkl. Import und Verwaltung</td></tr>
<tr><td>Planer</td><td>Stammdaten pflegen, Aufträge planen</td></tr>
<tr><td>Freigeber</td><td>Aufträge freigeben</td></tr>
<tr><td>Techniker</td><td>Aufträge ausführen</td></tr>
<tr><td>Betrachter</td><td>nur lesen</td></tr></table>
<p>Rollen sind kombinierbar. Der letzte aktive Administrator kann nicht entfernt werden.</p>
<h3>API-Zugänge</h3>
<p>Tokens für Skripte (Präfix <code>opp_</code>). Umfang <i>read</i> oder <i>write</i>, optional mit Ablauf. Der Klartext wird nur einmal angezeigt; Übergabe im Header <code>Authorization: Bearer …</code> bzw. <code>X-Auth-Token</code>.</p>
<h3>Audit-Log</h3>
<p>Protokolliert Anmeldungen, Änderungen an Stammdaten, Importe sowie Benutzer- und Token-Verwaltung.</p>` },

  { id: 'ausblick', title: 'Ausblick', html: `
<ul><li>Verbindungen und Patchaufträge mit Freigabe und Verlauf</li>
<li>Schnittstelle zu OpenPlan (Aufgaben für die Ausführung)</li>
<li>Soll/Ist-Abgleich über LLDP</li>
<li>Durchgängige Pfadansicht über Patchfelder und Dosen</li></ul>` },
]
