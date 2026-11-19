<template>
  <div class="max-w-6xl space-y-4">
    <router-link to="/devices" class="text-xs text-ks-600 dark:text-ks-400 hover:underline">← Alle Geräte</router-link>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

    <template v-if="d">
      <div class="flex items-start justify-between">
        <div>
          <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ d.hostname }}</h1>
          <p class="text-xs text-slate-400">{{ typeLabel(d.type) }} · {{ sourceLabel(d.source) }}<span v-if="d.ext_id"> · Quell-ID {{ d.ext_id }}</span></p>
        </div>
        <button v-if="canWrite" :class="btnDanger" @click="removeDevice">Gerät löschen</button>
      </div>

      <div :class="card" class="p-4">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">Stammdaten</h2>
        <p v-if="msg" class="text-sm mb-2" :class="msgErr ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ msg }}</p>
        <div class="grid md:grid-cols-3 gap-3">
          <div><label :class="lbl">Hostname</label><input v-model="form.hostname" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Typ</label><select v-model="form.type" :class="inp" :disabled="!canWrite"><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ l }}</option></select></div>
          <div><label :class="lbl">Status</label><select v-model="form.status" :class="inp" :disabled="!canWrite"><option v-for="[k, l] in DEVICE_STATUS" :key="k" :value="k">{{ l }}</option></select></div>
          <div><label :class="lbl">Hersteller</label><input v-model="form.vendor" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Modell</label><input v-model="form.model" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Seriennummer</label><input v-model="form.serial" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Mgmt-IP</label><input v-model="form.mgmt_ip" :class="inp" :disabled="!canWrite" /></div>
          <div>
            <label :class="lbl">Location <HelpHint text="Raum oder Rack des Geräts. Eine HE-Position ist nur in einem Rack möglich." /></label>
            <select v-model="form.location_id" :class="inp" :disabled="!canWrite"><option :value="null">(keine)</option>
              <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.path }}</option></select>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div><label :class="lbl">HE-Position</label><input v-model.number="form.rack_position" type="number" min="1" :class="inp" :disabled="!canWrite" /></div>
            <div><label :class="lbl">Höhe (HE)</label><input v-model.number="form.height_u" type="number" min="1" max="50" :class="inp" :disabled="!canWrite" /></div>
          </div>
          <div class="md:col-span-3"><label :class="lbl">Notiz</label><input v-model="form.note" :class="inp" :disabled="!canWrite" /></div>
        </div>
        <div v-if="canWrite" class="mt-3 text-right"><button :class="btnPrimary" @click="save">Speichern</button></div>
      </div>

      <div :class="card" class="p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Ports ({{ d.ports.length }})</h2>
          <div v-if="canWrite" class="flex gap-2">
            <button :class="btnGhost" @click="openBulk">Mehrere anlegen</button>
            <button :class="btnPrimary" @click="openPort()">+ Port</button>
          </div>
        </div>
        <p v-if="!d.ports.length" class="text-sm text-slate-400">Noch keine Ports.</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Name</th><th :class="th">Medium</th><th :class="th">Geschw.</th><th :class="th">Beschreibung</th>
              <th :class="th">Status</th><th v-if="d.type === 'patchpanel'" :class="th">Gegenseite</th>
              <th :class="th">Verbunden mit</th><th v-if="canWrite" :class="th"></th></tr></thead>
            <tbody>
              <tr v-for="p in d.ports" :key="p.id" class="border-t border-slate-100 dark:border-slate-700">
                <td :class="td" class="font-mono text-xs">{{ p.name }}</td>
                <td :class="td">{{ p.medium }}</td>
                <td :class="td">{{ fmtSpeed(p.speed_mbps) }}</td>
                <td :class="td" class="text-slate-500">{{ p.description || '–' }}</td>
                <td :class="td"><span :class="linkClass(p.oper_status)">{{ p.oper_status || '–' }}</span></td>
                <td v-if="d.type === 'patchpanel'" :class="td" class="text-xs font-mono">{{ p.peer_port_name || (p.peer_port_id ? `#${p.peer_port_id}` : '–') }}</td>
                <td :class="td" class="text-xs">
                  <router-link v-if="p.cable" :to="`/devices/${p.cable.device_id}`"
                    class="text-ks-600 dark:text-ks-400 hover:underline font-mono">
                    {{ p.cable.device_hostname }}:{{ p.cable.port_name }}
                  </router-link>
                  <span v-if="p.cable && p.cable.cable_label" class="ml-1 text-slate-400">({{ p.cable.cable_label }})</span>
                  <span v-if="p.cable && p.cable.measurement_ok === true" class="ml-1 text-green-500" title="Messung bestanden">✓</span>
                  <span v-if="p.cable && p.cable.measurement_ok === false" class="ml-1 text-red-500" title="Messung nicht bestanden">✗</span>
                  <span v-if="!p.cable" class="text-slate-400">–</span>
                </td>
                <td v-if="canWrite" :class="td" class="text-right whitespace-nowrap">
                  <button :class="btnLink" @click="openPort(p)">Bearbeiten</button>
                  <button v-if="d.type === 'patchpanel'" :class="btnLink" class="ml-3" @click="openPeer(p)">Gegenseite</button>
                  <button :class="btnLink" class="ml-3" @click="openLink(p)">Verbindung</button>
                  <button :class="btnDanger" class="ml-3" @click="removePort(p)">Löschen</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <ModalDialog v-if="portForm" :title="portForm.id ? 'Port bearbeiten' : 'Neuer Port'" :error="formError" @close="portForm = null">
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Name</label><input v-model="portForm.name" :class="inp" /></div>
        <div><label :class="lbl">Medium</label><select v-model="portForm.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
        <div><label :class="lbl">Geschwindigkeit (Mbit/s)</label><input v-model.number="portForm.speed_mbps" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">Beschreibung</label><input v-model="portForm.description" :class="inp" /></div>
      </div>
      <template #footer>
        <button @click="portForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="savePort" :class="btnPrimary" :disabled="!portForm.name">Speichern</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="bulk" title="Mehrere Ports anlegen" :error="formError" @close="bulk = null">
      <p class="text-xs text-slate-400 mb-1">Beispiel: Präfix <code>Port </code>, Start 1, Anzahl 24 legt Port 1–24 an.</p>
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">Präfix</label><input v-model="bulk.prefix" :class="inp" /></div>
        <div><label :class="lbl">Start</label><input v-model.number="bulk.start" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">Anzahl</label><input v-model.number="bulk.count" type="number" min="1" max="512" :class="inp" /></div>
        <div><label :class="lbl">Medium</label><select v-model="bulk.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
        <div><label :class="lbl">Mbit/s</label><input v-model.number="bulk.speed_mbps" type="number" min="0" :class="inp" /></div>
        <div class="flex flex-col gap-1">
          <label :class="lbl">Dual (Vorder-/Rückseite) <HelpHint text="Legt pro Port-Nummer zwei Ports an (z.B. &#x27;Port 1&#x27; und &#x27;Port 1-back&#x27;) und verbindet sie automatisch als Peer (Durchschleifung). Ideal für Patchfelder und Datendosen." /></label>
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" v-model="bulk.dual" class="rounded" />
            Vorder- und Rückseite anlegen
          </label>
        </div>
        <div v-if="bulk.dual"><label :class="lbl">Rückseiten-Suffix</label><input v-model="bulk.back_suffix" :class="inp" placeholder="-back" /></div>
      </div>
      <p v-if="bulk.dual" class="text-xs text-ks-600 dark:text-ks-400 mt-1">
        Legt {{ bulk.count * 2 }} Ports an: z.B. <code>{{ bulk.prefix }}{{ bulk.start }}</code> + <code>{{ bulk.prefix }}{{ bulk.start }}{{ bulk.back_suffix || '-back' }}</code> (automatisch gepeert)
      </p>
      <template #footer>
        <button @click="bulk = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveBulk" :class="btnPrimary" :disabled="!bulk.prefix || !bulk.count">Anlegen</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="cableForm" :title="`Kabel an ${cableForm.port.name}`" :error="formError" @close="cableForm = null">
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="col-span-2"><label :class="lbl">Zielgerät</label>
            <select v-model="cableForm.deviceId" :class="inp" @change="loadCablePorts">
              <option :value="null">(Verbindung lösen)</option>
              <option v-for="o in cableForm.devices" :key="o.id" :value="o.id">{{ o.hostname }}</option>
            </select>
          </div>
          <div v-if="cableForm.deviceId" class="col-span-2"><label :class="lbl">Zielport</label>
            <select v-model="cableForm.portId" :class="inp">
              <option :value="null">(Port wählen)</option>
              <option v-for="p in cableForm.ports" :key="p.id" :value="p.id">
                {{ p.name }}{{ p.cable ? ` ← belegt: ${p.cable.device_hostname}:${p.cable.port_name}` : '' }}
              </option>
            </select>
          </div>
        </div>
        <hr class="border-slate-200 dark:border-slate-700" />
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Kabeldetails</p>
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Kabelnummer / Label</label>
            <input v-model="cableForm.cable_label" :class="inp" placeholder="z.B. K-EG-001" />
          </div>
          <div><label :class="lbl">Kabeltyp</label>
            <select v-model="cableForm.cable_type" :class="inp">
              <option v-for="t in CABLE_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div v-if="cableForm.cable_type.startsWith('LWL')">
            <label :class="lbl">Faseranzahl</label>
            <input v-model.number="cableForm.fiber_count" type="number" min="1" :class="inp" placeholder="z.B. 4" />
          </div>
          <div><label :class="lbl">Länge (m)</label>
            <input v-model.number="cableForm.length_m" type="number" min="0" step="0.5" :class="inp" placeholder="z.B. 15.5" />
          </div>
          <div><label :class="lbl">Farbe</label>
            <input v-model="cableForm.color" :class="inp" placeholder="z.B. blau" />
          </div>
          <div><label :class="lbl">Verlegt am</label>
            <input v-model="cableForm.installed_at" type="date" :class="inp" />
          </div>
        </div>
        <hr class="border-slate-200 dark:border-slate-700" />
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Messprotokoll</p>
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Protokoll-Nr. / Referenz</label>
            <input v-model="cableForm.measurement_ref" :class="inp" placeholder="z.B. FLUKE-2024-001" />
          </div>
          <div><label :class="lbl">Messergebnis</label>
            <select v-model="cableForm.measurement_ok" :class="inp">
              <option :value="null">– nicht gemessen –</option>
              <option :value="true">✓ Bestanden</option>
              <option :value="false">✗ Nicht bestanden</option>
            </select>
          </div>
        </div>
        <div><label :class="lbl">Notiz</label>
          <input v-model="cableForm.note" :class="inp" placeholder="Freitext" />
        </div>
      </div>
      <template #footer>
        <button @click="cableForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveCable" :class="btnPrimary" :disabled="cableForm.deviceId !== null && !cableForm.portId">Speichern</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="peer" :title="`Gegenseite von ${peer.port.name}`" :error="formError" @close="peer = null">
      <p class="text-xs text-slate-400">Beim Patchfeld hängt jeder Port mit seiner Gegenseite (Rückseite/Vorderseite oder zweites Feld) zusammen. Wähle das Gerät und den Port.</p>
      <div><label :class="lbl">Gerät</label>
        <select v-model="peer.deviceId" :class="inp" @change="loadPeerPorts"><option :value="null">(wählen)</option>
          <option v-for="o in peer.devices" :key="o.id" :value="o.id">{{ o.hostname }}</option></select></div>
      <div v-if="peer.deviceId"><label :class="lbl">Port</label>
        <select v-model="peer.portId" :class="inp"><option :value="null">(Verbindung lösen)</option>
          <option v-for="p in peer.ports" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
      <template #footer>
        <button @click="peer = null" :class="btnGhost">Abbrechen</button>
        <button @click="savePeer" :class="btnPrimary">Speichern</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import HelpHint from '../components/HelpHint.vue'
import { api, errText, isAdmin } from '../api.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnDanger, btnLink, DEVICE_TYPES, DEVICE_STATUS, PORT_MEDIA,
         CABLE_TYPES, typeLabel, sourceLabel, fmtSpeed, linkClass } from '../ui.js'

const route = useRoute(), router = useRouter()
const canWrite = isAdmin()
const d = ref(null), locations = ref([])
const form = reactive({})
const error = ref(''), msg = ref(''), msgErr = ref(false), formError = ref('')
const portForm = ref(null), bulk = ref(null), peer = ref(null), cableForm = ref(null)

const FIELDS = ['hostname', 'type', 'vendor', 'model', 'serial', 'mgmt_ip', 'location_id', 'rack_position', 'height_u', 'status', 'note']

async function load() {
  try {
    d.value = await api.device(route.params.id)
    for (const k of FIELDS) form[k] = d.value[k]
    error.value = ''
  } catch (e) { error.value = errText(e, 'Gerät nicht gefunden'); d.value = null }
}

async function save() {
  msg.value = ''
  try {
    const body = { ...form, rack_position: form.rack_position || null, height_u: form.height_u || 1 }
    await api.updateDevice(d.value.id, body)
    msgErr.value = false; msg.value = 'Gespeichert'
    await load()
  } catch (e) { msgErr.value = true; msg.value = errText(e) }
}

async function removeDevice() {
  if (!confirm(`Gerät ${d.value.hostname} mit allen Ports löschen?`)) return
  try { await api.deleteDevice(d.value.id); router.push('/devices') } catch (e) { error.value = errText(e) }
}

function openPort(p) { formError.value = ''; portForm.value = p ? { ...p } : { name: '', medium: 'RJ45', speed_mbps: null, description: '' } }
async function savePort() {
  try {
    const f = { ...portForm.value, speed_mbps: portForm.value.speed_mbps || null }
    f.id ? await api.updatePort(f.id, f) : await api.createPort(d.value.id, f)
    portForm.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}
async function removePort(p) {
  if (!confirm(`Port ${p.name} löschen?`)) return
  try { await api.deletePort(p.id); await load() } catch (e) { error.value = errText(e) }
}

function openBulk() { formError.value = ''; bulk.value = { prefix: '', start: 1, count: 24, medium: 'RJ45', speed_mbps: null, dual: false, back_suffix: '-back' } }
async function saveBulk() {
  try {
    await api.bulkPorts(d.value.id, { ...bulk.value, speed_mbps: bulk.value.speed_mbps || null })
    bulk.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}

function _emptyCable() {
  return { cable_label: '', cable_type: 'other', fiber_count: null, length_m: null,
           color: '', installed_at: null, measurement_ref: '', measurement_ok: null, note: '' }
}
async function openLink(p) {
  formError.value = ''
  const r = await api.devices({ limit: 1000 })
  const devices = r.items.filter(o => o.id !== d.value.id)
  const currentDeviceId = p.cable ? p.cable.device_id : null
  let ports = []
  if (currentDeviceId) {
    const dev = await api.device(currentDeviceId)
    ports = dev.ports.filter(x => x.id !== p.id)
  }
  cableForm.value = {
    port: p, devices, ports,
    deviceId: currentDeviceId,
    portId: p.cable ? p.cable.port_id : null,
    ...(p.cable ? {
      cable_label: p.cable.cable_label, cable_type: p.cable.cable_type || 'other',
      fiber_count: p.cable.fiber_count, length_m: p.cable.length_m, color: p.cable.color,
      installed_at: p.cable.installed_at, measurement_ref: p.cable.measurement_ref,
      measurement_ok: p.cable.measurement_ok, note: p.cable.note,
    } : _emptyCable()),
  }
}
async function loadCablePorts() {
  cableForm.value.portId = null
  if (cableForm.value.deviceId) {
    const dev = await api.device(cableForm.value.deviceId)
    cableForm.value.ports = dev.ports.filter(x => x.id !== cableForm.value.port.id)
  } else {
    cableForm.value.ports = []
  }
}
async function saveCable() {
  try {
    const { port, devices, ports, deviceId, portId, ...cableFields } = cableForm.value
    await api.setCable(port.id, { port_b_id: portId, ...cableFields })
    cableForm.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}

async function openPeer(p) {
  formError.value = ''
  const r = await api.devices({ type: 'patchpanel', limit: 1000 })
  peer.value = { port: p, devices: r.items, deviceId: null, portId: p.peer_port_id || null, ports: [] }
}
async function loadPeerPorts() {
  peer.value.portId = null
  peer.value.ports = peer.value.deviceId ? (await api.device(peer.value.deviceId)).ports.filter(x => x.id !== peer.value.port.id) : []
}
async function savePeer() {
  try { await api.setPeer(peer.value.port.id, peer.value.portId); peer.value = null; await load() }
  catch (e) { formError.value = errText(e) }
}

onMounted(async () => { try { locations.value = await api.locations() } catch {} ; load() })
watch(() => route.params.id, id => { if (id) load() })
</script>
