<template>
  <div :class="{ dark: isDark }">
    <!-- Login-Seite: kein Layout -->
    <router-view v-if="$route.path === '/login'" />

    <!-- Normales Layout mit Sidebar -->
    <div v-else class="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-900">
      <AppSidebar @open-profile="showProfile = true" @toggle-help="showHelp = !showHelp" />
      <main class="flex-1 overflow-y-auto px-6 py-5">
        <router-view />
      </main>
    </div>
    <ProfileModal v-if="showProfile" @close="showProfile = false" />
    <HelpPanel :open="showHelp" @close="showHelp = false" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import AppSidebar from './components/AppSidebar.vue'
import ProfileModal from './components/ProfileModal.vue'
import HelpPanel from './components/HelpPanel.vue'

const isDark = ref(false)
const showProfile = ref(false)
const showHelp = ref(false)

function applyTheme() { isDark.value = localStorage.getItem('opp_theme') === 'dark' }

// F1 und ? schalten das Hilfe-Panel um (? nicht, wenn gerade in ein Eingabefeld getippt wird)
function onKey(e) {
  if (e.key === 'F1') { e.preventDefault(); showHelp.value = !showHelp.value; return }
  const t = e.target
  const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement || t?.isContentEditable
  if (e.key === '?' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) showHelp.value = !showHelp.value
}

onMounted(() => { applyTheme(); window.addEventListener('keydown', onKey) })
onUnmounted(() => window.removeEventListener('keydown', onKey))
window.addEventListener('storage', applyTheme)
</script>
