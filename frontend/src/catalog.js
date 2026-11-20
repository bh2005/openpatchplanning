// Gemeinsamer Zwischenspeicher für den Katalog (Kabelarten), damit Formulare ihn nicht einzeln laden.
import { ref } from 'vue'
import { api } from './api.js'

export const cableTypes = ref([])

export async function loadCableTypes(force = false) {
  if (cableTypes.value.length && !force) return
  try { cableTypes.value = await api.cableTypes() } catch { /* Formular zeigt dann eine leere Liste */ }
}

/** Beschriftung des Zählfelds (Fasern, Adern, Paare) einer Kabelart; leer = Kabelart hat keine Anzahl. */
export const countLabel = name => (cableTypes.value.find(t => t.name === name) || {}).count_label || ''
export const cableCategory = name => (cableTypes.value.find(t => t.name === name) || {}).category || 'other'
