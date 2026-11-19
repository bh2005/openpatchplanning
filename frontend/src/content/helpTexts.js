// Kontexthilfe pro Seite (F1 / ?). Schlüssel: Route, optional mit "#tab" für Seiten mit Reitern.
const T = {
  '/dashboard': `<h2>Übersicht</h2>
<p>Hier siehst du auf einen Blick, was im Bestand liegt: Standorte, Racks, Geräte und Ports.</p>
<ul><li><b>Geräte ohne Location</b> sind noch keinem Raum oder Rack zugeordnet – sie fehlen in der Rack-Ansicht.</li>
<li><b>Letzte Importe</b> zeigt, ob ein Import angewendet oder nur als Trockenlauf geprüft wurde.</li></ul>
<p class="help-tip">Neu hier? Lege zuerst Standorte an und importiere dann Geräte (Import).</p>`,

  '/sites': `<h2>Standorte</h2>
<p>Die Ortsstruktur ist hierarchisch: <b>Standort → Gebäude → Etage → Raum → Rack</b>.</p>
<ul><li>Wähle links einen Standort, rechts erscheint seine Struktur.</li>
<li>Ein <b>Rack</b> braucht die Anzahl Höheneinheiten (HE), damit die Rack-Ansicht sie darstellen kann.</li>
<li>Standorte oder Locations mit Geräten lassen sich nicht löschen.</li></ul>
<p class="help-tip">Beim Import genügt ein Pfad wie <code>SITE-A/Gebäude 1/Raum 2/Rack 3</code> – fehlende Ebenen werden angelegt.</p>`,

  '/devices': `<h2>Geräte</h2>
<p>Alle Geräte mit Ports: Switches, Router, Firewalls, Access Points, Server, Patchfelder und Dosen.</p>
<ul><li>Filter nach Suchtext, Typ, Status, Quelle und Standort sind kombinierbar.</li>
<li><b>Quelle</b> zeigt, woher das Gerät kommt (manuell, CSV, Checkmk …).</li>
<li>Klick auf einen Hostnamen öffnet Details und Ports.</li></ul>`,

  '/racks': `<h2>Racks</h2>
<p>Schrankansicht mit Höheneinheiten (HE). Die HE 1 ist unten.</p>
<ul><li>Geräte mit HE-Position werden an ihrer Stelle gezeigt, mehrhöhige Geräte über mehrere HE.</li>
<li>Geräte im Rack ohne HE-Position stehen darunter in der Liste „Ohne Position“.</li></ul>
<p class="help-tip">Die HE-Position trägst du am Gerät ein. Überschneidungen und Überschreiten der Rackhöhe werden abgewiesen.</p>`,

  '/import': `<h2>Import</h2>
<p>Geräte und Ports lassen sich aus CSV, JSON oder Checkmk einlesen. Der Import ändert nur Geräte und Ports, nie Verbindungen.</p>
<ul><li><b>Trockenlauf</b> berechnet alles und zeigt das Ergebnis, ohne zu speichern.</li>
<li><b>Atomar</b>: bei einem Fehler wird nichts gespeichert.</li>
<li>Wiederholte Importe sind sicher: Geräte werden über Hostname oder Quell-ID wiedererkannt. Leere Felder überschreiben nichts, fehlende Ports werden nicht gelöscht.</li></ul>`,
  '/import#csv': `<h2>CSV-Import</h2>
<p>Datei wählen, Spalten zuordnen, Trockenlauf prüfen, dann importieren. Die Zuordnung wird vorgeschlagen; passe sie bei Bedarf an.</p>
<ul><li><b>Geräte</b>: Pflichtfeld Hostname.</li><li><b>Ports</b>: Pflichtfelder Hostname und Port.</li></ul>`,
  '/import#json': `<h2>JSON-Import</h2>
<p>Dasselbe Format nutzt die API (<code>POST /api/import/json</code>) für Skripte. Ein Beispiel steht unter dem Eingabefeld.</p>`,
  '/import#checkmk': `<h2>Checkmk-Import</h2>
<p>Das Skript <code>tools/checkmk_export.py</code> liest das HW/SW-Inventar aus Checkmk und sendet es an die API. Dafür brauchst du einen API-Zugang mit Schreibrecht (Verwaltung → API-Zugänge).</p>`,

  '/admin': `<h2>Verwaltung</h2>
<p>Benutzer, API-Zugänge und Audit-Log. Nur für Administratoren.</p>`,
  '/admin#users': `<h2>Benutzer</h2>
<ul><li>Rollen sind kombinierbar: Administrator, Planer, Freigeber, Techniker, Betrachter.</li>
<li>„Sitzungen beenden“ meldet den Benutzer überall ab.</li>
<li>Der letzte aktive Administrator kann nicht entfernt oder entzogen werden.</li></ul>`,
  '/admin#tokens': `<h2>API-Zugänge</h2>
<p>Tokens für Skripte und Integrationen (z. B. Checkmk, OpenPlan). Der Klartext wird <b>nur einmal</b> bei der Erstellung angezeigt.</p>
<ul><li><b>read</b>: nur lesen. <b>write</b>: lesen und schreiben (Import).</li></ul>`,
  '/admin#audit': `<h2>Audit-Log</h2>
<p>Wer hat wann was geändert: Anmeldungen, Stammdaten, Importe, Benutzer- und Token-Verwaltung.</p>`,

  '/handbuch': `<h2>Handbuch</h2><p>Das Handbuch beschreibt alle Funktionen ausführlich. Über das Inhaltsverzeichnis springst du zu den Abschnitten.</p>`,
}

const DEFAULT = '<h2>Hilfe</h2><p>Für diese Seite gibt es keinen eigenen Hilfetext. Das Handbuch erklärt alle Funktionen.</p>'

export function getHelp(path, ctx = '') {
  const base = path.startsWith('/devices/') ? '/devices' : path
  return (ctx && T[`${base}#${ctx}`]) || T[base] || DEFAULT
}
