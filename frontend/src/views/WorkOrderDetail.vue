<template>
  <div class="max-w-5xl space-y-5" v-if="wo">
    <!-- Kopfzeile -->
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <div class="flex items-center gap-3">
          <button class="text-sm text-slate-400 hover:text-ks-600 dark:hover:text-ks-400" @click="$router.push('/workorders')">← Aufträge</button>
          <span class="font-mono font-semibold text-ks-700 dark:text-ks-400 text-lg">{{ wo.number }}</span>
          <span :class="statusClass(wo.status)" class="px-2 py-0.5 rounded-full text-xs font-medium">{{ wo.status_label }}</span>
          <span :class="prioClass(wo.priority)" class="text-xs font-medium">{{ prioLabel(wo.priority) }}</span>
        </div>
        <h1 class="text-xl font-semibold text-slate-800 dark:text-slate-100 mt-1">{{ wo.title }}</h1>
        <p v-if="wo.description" class="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{{ wo.description }}</p>
      </div>
      <div class="flex gap-2 flex-wrap">
        <button v-if="canEdit" :class="btnGhost" @click="openEdit">Bearbeiten</button>
        <template v-for="btn in actionButtons" :key="btn.action">
          <button :class="btn.danger ? btnDanger2 : btnPrimary" @click="doTransition(btn.action)" :disabled="transitioning">
            {{ btn.label }}
          </button>
        </template>
      </div>
    </div>

    <!-- Metadaten -->
    <div :class="card" class="p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div><span :class="metaLbl">Erstellt von</span><span class="text-slate-700 dark:text-slate-200">{{ wo.created_by }}</span></div>
      <div><span :class="metaLbl">Erstellt am</span><span class="text-slate-700 dark:text-slate-200">{{ fmtTime(wo.created_at) }}</span></div>
      <div v-if="wo.planned_from"><span :class="metaLbl">Geplant von</span><span class="text-slate-700 dark:text-slate-200">{{ wo.planned_from }}</span></div>
      <div v-if="wo.planned_to"><span :class="metaLbl">Geplant bis</span><span class="text-slate-700 dark:text-slate-200">{{ wo.planned_to }}</span></div>
      <div v-if="wo.location"><span :class="metaLbl">Standort</span><span class="text-slate-700 dark:text-slate-200">{{ wo.location.name }}</span></div>
      <div v-if="wo.note"><span :class="metaLbl">Notiz</span><span class="text-slate-700 dark:text-slate-200">{{ wo.note }}</span></div>
    </div>

    <!-- Fortschritt -->
    <div :class="card" class="p-4">
      <div class="flex gap-1 items-center flex-wrap">
        <template v-for="(step, i) in STEPS" :key="step.s">
          <div class="flex items-center gap-1">
            <span :class="[
              'px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
              wo.status === step.s ? statusClass(step.s) :
              STEP_IDX[wo.status] > i ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400 opacity-70' :
              'bg-slate-100 text-slate-400 dark:bg-slate-700 dark:text-slate-500'
            ]">{{ step.l }}</span>
            <span v-if="i < STEPS.length-1" class="text-slate-300 dark:text-slate-600 text-xs">→</span>
          </div>
        </template>
      </div>
    </div>

    <!-- Positionen -->
    <div :class="card" class="overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Positionen ({{ wo.items.length }})</h2>
        <button v-if="canEditItems" :class="btnPrimary" class="text-xs px-3 py-1.5" @click="openAddItem">+ Position</button>
      </div>
      <p v-if="!wo.items.length" class="p-6 text-sm text-slate-400">Noch keine Positionen. Füge Verbindungen hinzu, die hergestellt oder getrennt werden sollen.</p>
      <table v-else class="w-full text-sm">
        <thead class="bg-slate-50 dark:bg-slate-700/50">
          <tr>
            <th :class="th">Aktion</th>
            <th :class="th">Port A</th>
            <th :class="th">Port B</th>
            <th :class="th">Kabel</th>
            <th :class="th">Status</th>
            <th :class="th"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in wo.items" :key="item.id" class="border-t border-slate-100 dark:border-slate-700">
            <td :class="td"><span :class="actionClass(item.action)" class="text-xs font-medium">{{ actionLabel(item.action) }}</span></td>
            <td :class="td" class="font-mono text-xs">
              <span v-if="item.port_a" class="text-slate-700 dark:text-slate-200">{{ item.port_a.device_hostname }}:{{ item.port_a.name }}</span>
              <span v-else class="text-slate-400">–</span>
            </td>
            <td :class="td" class="font-mono text-xs">
              <span v-if="item.port_b" class="text-slate-700 dark:text-slate-200">{{ item.port_b.device_hostname }}:{{ item.port_b.name }}</span>
              <span v-else class="text-slate-400">–</span>
              <span v-if="item.old_port_b" class="text-slate-400 ml-1">(war: {{ item.old_port_b.device_hostname }}:{{ item.old_port_b.name }})</span>
            </td>
            <td :class="td" class="text-xs text-slate-500">
              <span v-if="item.cable_label" class="font-mono text-slate-700 dark:text-slate-200">{{ item.cable_label }}</span>
              <span v-if="item.cable_type !== 'other'" class="ml-1 text-slate-400">{{ item.cable_type }}</span>
              <span v-if="item.length_m" class="ml-1 text-slate-400">{{ item.length_m }}m</span>
            </td>
            <td :class="td">
              <span :class="itemStatusClass(item.item_status)" class="px-2 py-0.5 rounded-full text-xs font-medium">
                {{ itemStatusLabel(item.item_status) }}
              </span>
              <span v-if="item.deviation_note" class="ml-1 text-xs text-orange-500" :title="item.deviation_note">⚠</span>
            </td>
            <td :class="td" class="text-right whitespace-nowrap">
              <button v-if="canEditItems" :class="btnDanger" @click="deleteItem(item)" class="mr-1">Löschen</button>
              <button v-if="canExecuteItem(item)" :class="btnLink" @click="openExecItem(item)">Abhaken</button>
              <button v-if="canReopenItem(item)" :class="btnLink" @click="reopenItem(item)">Zurücksetzen</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="err" class="text-sm text-red-500">{{ err }}</p>

    <!-- Dialog: Auftrag bearbeiten -->
    <Teleport to="body">
      <div v-if="editDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="editDialog=false">
        <div :class="card" class="w-full max-w-lg p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Auftrag bearbeiten</h2>
          <div><label :class="lbl">Titel *</label><input v-model="editForm.title" :class="inp" /></div>
          <div><label :class="lbl">Beschreibung</label><textarea v-model="editForm.description" :class="inp" rows="3" /></div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label :class="lbl">Priorität</label>
              <select v-model="editForm.priority" :class="inp">
                <option v-for="[v, l] in PRIO_OPTIONS" :key="v" :value="v">{{ l }}</option>
              </select>
            </div>
            <div><label :class="lbl">Von</label><input v-model="editForm.planned_from" type="date" :class="inp" /></div>
          </div>
          <div><label :class="lbl">Bis</label><input v-model="editForm.planned_to" type="date" :class="inp" /></div>
          <div><label :class="lbl">Notiz</label><textarea v-model="editForm.note" :class="inp" rows="2" /></div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="editDialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="saveEdit" :disabled="saving">{{ saving ? '…' : 'Speichern' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Dialog: Position hinzufügen/bearbeiten -->
    <Teleport to="body">
      <div v-if="itemDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="itemDialog=false">
        <div :class="card" class="w-full max-w-xl p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Position</h2>
          <div>
            <label :class="lbl">Aktion</label>
            <select v-model="itemForm.action" :class="inp">
              <option value="connect">Verbindung herstellen</option>
              <option value="disconnect">Verbindung trennen</option>
              <option value="move">Verbindung umstecken</option>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label :class="lbl">Port A (Gerät:Port-ID)</label>
              <input v-model.number="itemForm.port_a_id" type="number" :class="inp" placeholder="Port-ID" />
            </div>
            <div>
              <label :class="lbl">{{ itemForm.action === 'move' ? 'Neuer Port B' : 'Port B' }}</label>
              <input v-model.number="itemForm.port_b_id" type="number" :class="inp" placeholder="Port-ID" />
            </div>
          </div>
          <div v-if="itemForm.action === 'move'">
            <label :class="lbl">Alter Port B (bisherige Verbindung)</label>
            <input v-model.number="itemForm.old_port_b_id" type="number" :class="inp" placeholder="Port-ID" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div><label :class="lbl">Kabelnummer</label><input v-model="itemForm.cable_label" :class="inp" /></div>
            <div>
              <label :class="lbl">Kabeltyp</label>
              <select v-model="itemForm.cable_type" :class="inp">
                <option v-for="t in CABLE_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-3">
            <div><label :class="lbl">Länge (m)</label><input v-model.number="itemForm.length_m" type="number" step="0.1" :class="inp" /></div>
            <div><label :class="lbl">Faseranzahl</label><input v-model.number="itemForm.fiber_count" type="number" :class="inp" /></div>
            <div><label :class="lbl">Farbe</label><input v-model="itemForm.color" :class="inp" /></div>
          </div>
          <div><label :class="lbl">Notiz</label><input v-model="itemForm.note" :class="inp" /></div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="itemDialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="saveItem" :disabled="saving">{{ saving ? '…' : 'Speichern' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Dialog: Abhaken -->
    <Teleport to="body">
      <div v-if="execDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="execDialog=false">
        <div :class="card" class="w-full max-w-md p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Position abhaken</h2>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            <span class="font-mono">{{ execItem?.port_a?.device_hostname }}:{{ execItem?.port_a?.name }}</span>
            {{ actionLabel(execItem?.action) }}
            <span class="font-mono">{{ execItem?.port_b?.device_hostname }}:{{ execItem?.port_b?.name }}</span>
          </p>
          <div>
            <label :class="lbl">Ergebnis</label>
            <select v-model="execForm.item_status" :class="inp">
              <option value="done">Erledigt</option>
              <option value="deviation">Abweichung</option>
            </select>
          </div>
          <div v-if="execForm.item_status === 'deviation'">
            <label :class="lbl">Abweichungsnotiz *</label>
            <textarea v-model="execForm.deviation_note" :class="inp" rows="2" placeholder="Was war anders?" />
          </div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="execDialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="saveExec" :disabled="saving">{{ saving ? '…' : 'Bestätigen' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>

  <div v-else-if="loading" class="text-sm text-slate-400 p-8">Lade…</div>
  <div v-else class="text-sm text-red-500 p-8">{{ err }}</div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, errText, hasRole, isAdmin } from '../api.js'
import { card, inp, lbl, th, td, btnPrimary, btnGhost, btnDanger, btnLink, fmtTime } from '../ui.js'
import { CABLE_TYPES } from '../ui.js'

const route = useRoute()
const wo = ref(null), loading = ref(true), err = ref(''), transitioning = ref(false), saving = ref(false)
const editDialog = ref(false), itemDialog = ref(false), execDialog = ref(false)
const dialogErr = ref('')
const editForm = ref({})
const itemForm = ref({})
const execForm = ref({ item_status: 'done', deviation_note: '' })
const execItem = ref(null)
const editingItemId = ref(null)

const STEPS = [
  {s:'draft',l:'Entwurf'},{s:'submitted',l:'Eingereicht'},{s:'approved',l:'Freigegeben'},
  {s:'in_progress',l:'In Ausführung'},{s:'done',l:'Ausgeführt'},{s:'confirmed',l:'Bestätigt'},
]
const STEP_IDX = Object.fromEntries(STEPS.map((s, i) => [s.s, i]))
const PRIO_OPTIONS = [['low','Niedrig'],['normal','Normal'],['high','Hoch'],['critical','Kritisch']]
const metaLbl = 'block text-xs text-slate-400 uppercase tracking-wide mb-0.5'
const btnDanger2 = 'bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors shadow-sm'

const ACTION_BUTTONS = {
  draft:       [{action:'submit',   label:'Einreichen',       roles:['planer']}],
  submitted:   [{action:'approve',  label:'Freigeben',        roles:['freigeber']},
                {action:'reject',   label:'Ablehnen',         danger:true, roles:['freigeber']}],
  approved:    [{action:'start',    label:'Ausführung starten', roles:['techniker']}],
  in_progress: [{action:'finish',   label:'Ausführung abschließen', roles:['techniker']}],
  done:        [{action:'confirm',  label:'Bestätigen & anwenden', roles:['freigeber']},
                {action:'rework',   label:'Nacharbeit', danger:true, roles:['freigeber']}],
  rework:      [{action:'start',    label:'Ausführung starten', roles:['techniker']}],
}

const actionButtons = computed(() => {
  if (!wo.value) return []
  return (ACTION_BUTTONS[wo.value.status] || []).filter(b =>
    isAdmin() || hasRole(...b.roles)
  )
})
const canEdit = computed(() => wo.value && ['draft','rework'].includes(wo.value.status) && (isAdmin() || hasRole('planer')))
const canEditItems = computed(() => wo.value && ['draft','rework'].includes(wo.value.status) && (isAdmin() || hasRole('planer')))
const canExecuteItem = item => wo.value?.status === 'in_progress' && item.item_status === 'open' && (isAdmin() || hasRole('techniker'))
const canReopenItem = item => wo.value?.status === 'in_progress' && item.item_status !== 'open' && (isAdmin() || hasRole('techniker'))

const statusClass = s => ({
  draft:'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  submitted:'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  approved:'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
  rejected:'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  in_progress:'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  done:'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  confirmed:'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  rework:'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
}[s] || 'bg-slate-100 text-slate-500')

const prioClass = p => ({ low:'text-slate-400', normal:'text-slate-600 dark:text-slate-300',
  high:'text-amber-600 dark:text-amber-400', critical:'text-red-600 dark:text-red-400 font-semibold' }[p] || '')
const prioLabel = p => ({ low:'Niedrig', normal:'Normal', high:'Hoch', critical:'Kritisch' }[p] || p)
const actionLabel = a => ({ connect:'→ herstellen', disconnect:'✕ trennen', move:'↔ umstecken' }[a] || a)
const actionClass = a => ({ connect:'text-green-700 dark:text-green-400', disconnect:'text-red-600 dark:text-red-400',
  move:'text-blue-600 dark:text-blue-400' }[a] || '')
const itemStatusLabel = s => ({ open:'offen', done:'erledigt', deviation:'Abweichung' }[s] || s)
const itemStatusClass = s => ({ open:'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
  done:'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  deviation:'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' }[s] || '')

async function load() {
  try {
    wo.value = await api.workorder(route.params.id)
    err.value = ''
  } catch (e) { err.value = errText(e) }
  finally { loading.value = false }
}

async function doTransition(action) {
  transitioning.value = true
  try {
    wo.value = await api.workorderTransition(wo.value.id, action)
    err.value = ''
  } catch (e) { err.value = errText(e) }
  finally { transitioning.value = false }
}

function openEdit() {
  editForm.value = { ...wo.value, location_id: wo.value.location?.id }
  dialogErr.value = ''
  editDialog.value = true
}

async function saveEdit() {
  if (!editForm.value.title.trim()) { dialogErr.value = 'Titel ist erforderlich'; return }
  saving.value = true
  try {
    wo.value = await api.updateWorkorder(wo.value.id, editForm.value)
    editDialog.value = false
  } catch (e) { dialogErr.value = errText(e) }
  finally { saving.value = false }
}

function openAddItem() {
  editingItemId.value = null
  itemForm.value = { action:'connect', port_a_id: null, port_b_id: null, old_port_b_id: null,
    cable_label:'', cable_type:'Cat6', fiber_count: null, length_m: null, color:'', note:'', idx: wo.value.items.length }
  dialogErr.value = ''
  itemDialog.value = true
}

async function saveItem() {
  saving.value = true
  try {
    if (editingItemId.value) {
      const updated = await api.updateWorkitem(wo.value.id, editingItemId.value, itemForm.value)
      const idx = wo.value.items.findIndex(i => i.id === editingItemId.value)
      if (idx >= 0) wo.value.items[idx] = updated
    } else {
      const item = await api.addWorkitem(wo.value.id, itemForm.value)
      wo.value.items.push(item)
    }
    itemDialog.value = false
  } catch (e) { dialogErr.value = errText(e) }
  finally { saving.value = false }
}

async function deleteItem(item) {
  if (!confirm(`Position löschen?`)) return
  try {
    await api.deleteWorkitem(wo.value.id, item.id)
    wo.value.items = wo.value.items.filter(i => i.id !== item.id)
  } catch (e) { err.value = errText(e) }
}

function openExecItem(item) {
  execItem.value = item
  execForm.value = { item_status: 'done', deviation_note: '' }
  dialogErr.value = ''
  execDialog.value = true
}

async function saveExec() {
  if (execForm.value.item_status === 'deviation' && !execForm.value.deviation_note.trim()) {
    dialogErr.value = 'Bitte Abweichungsnotiz eingeben'; return
  }
  saving.value = true
  try {
    const updated = await api.executeWorkitem(wo.value.id, execItem.value.id, execForm.value)
    const idx = wo.value.items.findIndex(i => i.id === execItem.value.id)
    if (idx >= 0) wo.value.items[idx] = updated
    execDialog.value = false
  } catch (e) { dialogErr.value = errText(e) }
  finally { saving.value = false }
}

async function reopenItem(item) {
  try {
    const updated = await api.reopenWorkitem(wo.value.id, item.id)
    const idx = wo.value.items.findIndex(i => i.id === item.id)
    if (idx >= 0) wo.value.items[idx] = updated
  } catch (e) { err.value = errText(e) }
}

onMounted(load)
</script>
