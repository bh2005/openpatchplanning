<template>
  <div class="max-w-5xl space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Racks</h1>
      <select v-model="rackId" :class="inp" class="!w-80" @change="load">
        <option :value="null" disabled>Rack wählen …</option>
        <option v-for="r in racks" :key="r.id" :value="r.id">{{ r.path }} ({{ r.rack_units || '?' }} HE)</option>
      </select>
    </div>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
    <p v-if="loaded && !racks.length" class="text-sm text-slate-400">Noch kein Rack angelegt. Lege unter „Standorte“ eine Location der Art „Rack“ mit Höheneinheiten an.</p>

    <div v-if="rack" class="grid md:grid-cols-3 gap-4">
      <div :class="card" class="p-4 md:col-span-2">
        <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">{{ rack.path }}</h2>
        <div class="border-2 border-slate-400 dark:border-slate-500 rounded bg-slate-100 dark:bg-slate-900 inline-block min-w-[320px] w-full">
          <div v-for="row in rows" :key="row.u" class="flex border-b border-slate-200 dark:border-slate-700 last:border-b-0" :style="{ height: row.span * UNIT + 'px' }">
            <div class="w-8 text-[10px] text-slate-400 text-right pr-1.5 pt-0.5 flex-shrink-0 border-r border-slate-200 dark:border-slate-700">{{ row.u }}</div>
            <router-link v-if="row.device" :to="`/devices/${row.device.id}`"
              class="flex-1 px-2 flex items-center text-xs font-medium text-white bg-ks-600 hover:bg-ks-700 overflow-hidden whitespace-nowrap">
              {{ row.device.hostname }} <span class="ml-2 opacity-70 font-normal">{{ typeLabel(row.device.type) }} · {{ row.device.height_u }} HE</span>
            </router-link>
            <div v-else class="flex-1"></div>
          </div>
        </div>
      </div>

      <div :class="card" class="p-4">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Ohne Position</h2>
        <p v-if="!loose.length" class="text-sm text-slate-400">Alle Geräte im Rack haben eine HE-Position.</p>
        <ul class="text-sm space-y-1">
          <li v-for="x in loose" :key="x.id"><router-link :to="`/devices/${x.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ x.hostname }}</router-link>
            <span class="text-xs text-slate-400"> · {{ typeLabel(x.type) }}</span></li>
        </ul>
        <p class="text-xs text-slate-400 mt-3">{{ used }} von {{ rack.rack_units || '?' }} HE belegt.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, errText } from '../api.js'
import { inp, card, typeLabel } from '../ui.js'

const UNIT = 26                      // Pixel pro Höheneinheit
const racks = ref([]), rackId = ref(null), devices = ref([])
const error = ref(''), loaded = ref(false)
const rack = computed(() => racks.value.find(r => r.id === rackId.value) || null)

const placed = computed(() => devices.value.filter(x => x.rack_position))
const loose = computed(() => devices.value.filter(x => !x.rack_position))
const used = computed(() => placed.value.reduce((n, x) => n + x.height_u, 0))

// Zeilen von oben (höchste HE) nach unten; ein mehrhöhiges Gerät belegt eine Zeile mit span > 1
const rows = computed(() => {
  const total = rack.value?.rack_units || Math.max(0, ...placed.value.map(x => x.rack_position + x.height_u - 1))
  const out = []
  for (let u = total; u >= 1; u--) {
    const dev = placed.value.find(x => x.rack_position + x.height_u - 1 === u)
    if (dev) { out.push({ u, device: dev, span: dev.height_u }); u -= dev.height_u - 1 }
    else out.push({ u, device: null, span: 1 })
  }
  return out
})

async function load() {
  try {
    const r = await api.devices({ location_id: rackId.value, limit: 1000 })
    // Geräte untergeordneter Locations gehören nicht in die Schrankansicht
    devices.value = r.items.filter(x => x.location_id === rackId.value)
    error.value = ''
  } catch (e) { error.value = errText(e) }
}

onMounted(async () => {
  try {
    racks.value = (await api.locations()).filter(l => l.kind === 'rack')
    if (racks.value.length) { rackId.value = racks.value[0].id; await load() }
  } catch (e) { error.value = errText(e) }
  loaded.value = true
})
</script>
