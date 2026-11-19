// Gemeinsame Tailwind-Klassen und Beschriftungen (damit alle Seiten gleich aussehen).

export const inp = 'w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-100 focus:outline-none focus:border-ks-500 transition-colors disabled:opacity-60'
export const lbl = 'block text-xs font-medium text-slate-400 uppercase tracking-wide mb-1'
export const card = 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm'
export const btnPrimary = 'bg-ks-600 hover:bg-ks-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors shadow-sm'
export const btnGhost = 'bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50 text-slate-700 dark:text-slate-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors'
export const btnDanger = 'text-xs text-red-500 hover:text-red-700 hover:underline'
export const btnLink = 'text-xs text-ks-600 dark:text-ks-400 hover:underline'
export const th = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400'
export const td = 'px-3 py-2'

export const DEVICE_TYPES = [
  ['switch', 'Switch'], ['router', 'Router'], ['firewall', 'Firewall'], ['ap', 'Access Point'], ['server', 'Server'],
  ['patchpanel', 'Patchfeld'], ['outlet', 'Dose'], ['endpoint', 'Endgerät'], ['other', 'Sonstiges'],
]
export const DEVICE_STATUS = [['planned', 'geplant'], ['active', 'aktiv'], ['retired', 'außer Betrieb']]
export const LOCATION_KINDS = [['building', 'Gebäude'], ['floor', 'Etage'], ['room', 'Raum'], ['rack', 'Rack']]
export const PORT_MEDIA = ['RJ45', 'SFP', 'SFP+', 'SFP28', 'QSFP', 'LWL', 'other']
export const SOURCES = [['manual', 'manuell'], ['csv', 'CSV'], ['json', 'JSON'], ['api', 'API'], ['checkmk', 'Checkmk'], ['openplan', 'OpenPlan']]
export const ROLES = [
  ['admin', 'Administrator', 'darf alles'], ['planer', 'Planer', 'erstellt und reicht Patchaufträge ein'],
  ['freigeber', 'Freigeber', 'gibt Aufträge frei oder lehnt sie ab'], ['techniker', 'Techniker', 'führt Aufträge aus'],
  ['viewer', 'Betrachter', 'darf nur lesen'],
]

const labelOf = (list, key) => (list.find(x => x[0] === key) || [key, key])[1]
export const typeLabel = k => labelOf(DEVICE_TYPES, k)
export const statusLabel = k => labelOf(DEVICE_STATUS, k)
export const kindLabel = k => labelOf(LOCATION_KINDS, k)
export const sourceLabel = k => labelOf(SOURCES, k)
export const roleLabel = k => labelOf(ROLES, k)

export const statusClass = s => ({
  active:  'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  planned: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  retired: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
}[s] || 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300')

export const linkClass = s => ({
  up:   'text-green-600 dark:text-green-400',
  down: 'text-slate-400',
}[s] || 'text-slate-500')

export function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString('de-DE') : '–' }
export function fmtSpeed(m) { return !m ? '–' : (m >= 1000 ? `${m / 1000} Gbit/s` : `${m} Mbit/s`) }
