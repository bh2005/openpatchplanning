<template>
  <div class="max-w-5xl space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Patchaufträge</h1>
      <button v-if="canCreate" :class="btnPrimary" @click="openNew">+ Neuer Auftrag</button>
    </div>

    <!-- Filter -->
    <div class="flex gap-2 flex-wrap">
      <select v-model="filterStatus" :class="inp" class="w-48">
        <option value="">Alle Status</option>
        <option v-for="[v, l] in STATUS_OPTIONS" :key="v" :value="v">{{ l }}</option>
      </select>
      <input v-model="filterQ" :class="inp" class="flex-1 min-w-48" placeholder="Suche Nummer / Titel / Ersteller…" @keyup.enter="load" />
      <button :class="btnGhost" @click="load">Suchen</button>
    </div>

    <p v-if="err" class="text-sm text-red-500">{{ err }}</p>

    <div :class="card" class="overflow-hidden">
      <p v-if="!rows.length" class="p-6 text-sm text-slate-400">Keine Aufträge gefunden.</p>
      <table v-else class="w-full text-sm">
        <thead class="border-b border-slate-100 dark:border-slate-700">
          <tr>
            <th :class="th">Nummer</th>
            <th :class="th">Titel</th>
            <th :class="th">Status</th>
            <th :class="th">Priorität</th>
            <th :class="th">Positionen</th>
            <th :class="th">Erstellt</th>
            <th :class="th">Ersteller</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in rows" :key="w.id"
            class="border-t border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 cursor-pointer"
            @click="$router.push(`/workorders/${w.id}`)">
            <td :class="td" class="font-mono font-medium text-ks-700 dark:text-ks-400">{{ w.number }}</td>
            <td :class="td" class="font-medium text-slate-800 dark:text-slate-200 max-w-xs truncate">{{ w.title }}</td>
            <td :class="td"><span :class="statusClass(w.status)" class="px-2 py-0.5 rounded-full text-xs font-medium">{{ w.status_label }}</span></td>
            <td :class="td"><span :class="prioClass(w.priority)" class="text-xs font-medium">{{ prioLabel(w.priority) }}</span></td>
            <td :class="td" class="text-slate-500">{{ (w.items || []).length }}</td>
            <td :class="td" class="text-slate-500 whitespace-nowrap">{{ fmtTime(w.created_at) }}</td>
            <td :class="td" class="text-slate-500">{{ w.created_by }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Dialog: Neuer Auftrag -->
    <Teleport to="body">
      <div v-if="dialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="dialog=false">
        <div :class="card" class="w-full max-w-lg p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Neuer Patchauftrag</h2>
          <div>
            <label :class="lbl">Titel *</label>
            <input v-model="form.title" :class="inp" placeholder="z. B. Neue Dosen EG Raum 112" />
          </div>
          <div>
            <label :class="lbl">Beschreibung</label>
            <textarea v-model="form.description" :class="inp" rows="3" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label :class="lbl">Priorität</label>
              <select v-model="form.priority" :class="inp">
                <option v-for="[v, l] in PRIO_OPTIONS" :key="v" :value="v">{{ l }}</option>
              </select>
            </div>
            <div>
              <label :class="lbl">Zeitraum von</label>
              <input v-model="form.planned_from" type="date" :class="inp" />
            </div>
          </div>
          <div>
            <label :class="lbl">Zeitraum bis</label>
            <input v-model="form.planned_to" type="date" :class="inp" />
          </div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="dialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="save" :disabled="saving">{{ saving ? 'Speichere…' : 'Anlegen' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, errText, hasRole } from '../api.js'
import { card, inp, lbl, th, td, btnPrimary, btnGhost, fmtTime } from '../ui.js'

const STATUS_OPTIONS = [
  ['draft','Entwurf'],['submitted','Eingereicht'],['approved','Freigegeben'],
  ['rejected','Abgelehnt'],['in_progress','In Ausführung'],['done','Ausgeführt'],
  ['confirmed','Bestätigt'],['rework','Nacharbeit'],
]
const PRIO_OPTIONS = [['low','Niedrig'],['normal','Normal'],['high','Hoch'],['critical','Kritisch']]

const statusClass = s => ({
  draft:       'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  submitted:   'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  approved:    'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
  rejected:    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  done:        'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  confirmed:   'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  rework:      'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
}[s] || 'bg-slate-100 text-slate-500')

const prioClass = p => ({ low:'text-slate-400', normal:'text-slate-600 dark:text-slate-300',
  high:'text-amber-600 dark:text-amber-400', critical:'text-red-600 dark:text-red-400 font-semibold' }[p] || '')
const prioLabel = p => ({ low:'Niedrig', normal:'Normal', high:'Hoch', critical:'Kritisch' }[p] || p)

const rows = ref([])
const err = ref('')
const filterStatus = ref('')
const filterQ = ref('')
const dialog = ref(false)
const dialogErr = ref('')
const saving = ref(false)
const canCreate = hasRole('planer', 'admin')

const form = ref({ title: '', description: '', priority: 'normal', planned_from: '', planned_to: '' })

async function load() {
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    if (filterQ.value.trim()) params.q = filterQ.value.trim()
    rows.value = await api.workorders(params)
    err.value = ''
  } catch (e) { err.value = errText(e) }
}

function openNew() {
  form.value = { title: '', description: '', priority: 'normal', planned_from: '', planned_to: '' }
  dialogErr.value = ''
  dialog.value = true
}

async function save() {
  if (!form.value.title.trim()) { dialogErr.value = 'Titel ist erforderlich'; return }
  saving.value = true
  try {
    const wo = await api.createWorkorder(form.value)
    dialog.value = false
    rows.value.unshift(wo)
  } catch (e) { dialogErr.value = errText(e) }
  finally { saving.value = false }
}

onMounted(load)
</script>
