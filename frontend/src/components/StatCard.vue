<template>
  <div :class="card" class="px-4 py-3">
    <div class="text-xs uppercase tracking-wide text-slate-400">{{ label }}</div>
    <div class="text-2xl font-semibold text-slate-800 dark:text-slate-100 mt-0.5">{{ value }}</div>
    <div v-if="hint" class="text-[11px] mt-0.5" :class="warn ? 'text-amber-600 dark:text-amber-400' : 'text-slate-400'">{{ hint }}</div>
  </div>
</template>

<script setup>
import { card } from '../ui.js'
defineProps({ label: String, value: [Number, String], hint: String, warn: Boolean })
</script>
