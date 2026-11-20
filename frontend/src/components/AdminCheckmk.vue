<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">Mit der Adresse Ihrer Checkmk-Site erscheint bei Geräten (Racks, Gerätedetails) ein Link
      <b>„In Checkmk öffnen“</b>, der direkt die Host-Seite öffnet. Leer = kein Link.</p>
    <div class="max-w-xl space-y-3">
      <div><label :class="lbl">Adresse der Checkmk-Site</label>
        <input v-model="f.base_url" :class="inp" placeholder="https://monitoring.example.test/prod" />
        <p class="text-xs text-slate-400 mt-1">Mit Site-Namen, ohne Parameter. Der Hostname in Checkmk muss dem Hostnamen hier entsprechen.</p></div>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="f.link_all" /> Link auch für manuell angelegte Geräte (sonst nur Geräte aus dem Checkmk-Import)</label>
    </div>
    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">Speichern</button>
      <a v-if="f.base_url" :href="f.base_url + '/check_mk/'" target="_blank" rel="noopener" :class="btnLink">Site öffnen ↗</a>
      <span v-if="msg" class="text-sm text-green-600">{{ msg }}</span><span v-if="err" class="text-sm text-red-500">{{ err }}</span>
    </div>
    <div class="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-200 dark:border-slate-700 pt-3 max-w-2xl space-y-1">
      <p><b>Soll/Ist-Abgleich:</b> Die LLDP-/CDP-Nachbarn kommen mit dem Checkmk-Import (<code>tools/checkmk_export.py</code> auf dem Checkmk-Server; Beschreibung in <code>docs/checkmk-import.md</code>).
        Jeder Import ersetzt die Nachbarn der enthaltenen Geräte. Das Ergebnis steht unter „Soll/Ist“.</p>
    </div>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { loadCheckmk } from '../checkmk.js'
import { inp, lbl, btnPrimary, btnLink } from '../ui.js'

const f = reactive({ base_url: '', link_all: true })
const busy = ref(false), msg = ref(''), err = ref('')
onMounted(async () => { try { const c = await api.checkmkLink(); f.base_url = c.base_url; f.link_all = c.link_all } catch (e) { err.value = errText(e) } })
async function save() {
  busy.value = true; msg.value = err.value = ''
  try { await api.saveCheckmkLink({ base_url: f.base_url, link_all: f.link_all }); await loadCheckmk(true); msg.value = 'Gespeichert' }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
</script>
