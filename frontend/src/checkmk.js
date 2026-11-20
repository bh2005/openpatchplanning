// Link zur Hostseite in Checkmk (Adresse der Site in Verwaltung → Checkmk).
import { ref } from 'vue'
import { api } from './api.js'

const cfg = ref({ enabled: false, base_url: '', link_all: true })
let loaded = null

export function loadCheckmk(force = false) {
  if (!loaded || force) loaded = api.checkmkLink().then(c => { cfg.value = c }).catch(() => {})
  return loaded
}

const PASSIVE = ['patchpanel', 'outlet', 'cable_mgmt', 'blank_panel', 'shelf', 'power_supply']

// Adresse der Host-Ansicht oder '' (nicht eingerichtet, passives Gerät, bzw. nicht aus Checkmk importiert und „nur importierte“ gewählt)
export function checkmkUrl(device) {
  const c = cfg.value
  if (!c.enabled || !device || PASSIVE.includes(device.type) || device.status === 'retired') return ''
  if (!c.link_all && device.source !== 'checkmk') return ''
  return `${c.base_url}/check_mk/view.py?view_name=host&host=${encodeURIComponent(device.hostname)}`
}

export const checkmkConfig = cfg
