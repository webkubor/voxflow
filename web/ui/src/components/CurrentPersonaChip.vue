<template>
  <div v-if="selected" class="persona-chip" :class="{ 'is-empty': !hasAudio }">
    <n-avatar round :size="26" :style="{ background: 'var(--vf-bg-3)', color: 'var(--vf-primary)' }">
      {{ initial }}
    </n-avatar>
    <div class="chip-text">
      <span class="chip-label">当前音色</span>
      <span class="chip-name">{{ name }}</span>
    </div>
    <span class="chip-status" :class="hasAudio ? 'ok' : 'none'">
      {{ hasAudio ? '✓ 样音已装载' : '○ 纯文本' }}
    </span>
  </div>
  <div v-else class="persona-chip is-empty" @click="$emit('openLibrary')">
    <span class="empty-icon">🎙️</span>
    <span class="empty-text">尚未选择音色 · 点击左侧「音色库」挑选</span>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useVoicesStore } from '../stores/voices';

defineEmits(['openLibrary']);

const voicesStore = useVoicesStore();
const { personas, selectedPersona } = storeToRefs(voicesStore);

const selected = computed(() => !!selectedPersona.value);
const persona = computed(() => (selectedPersona.value ? personas.value[selectedPersona.value] : null));
const name = computed(() => persona.value?.name || selectedPersona.value || '');
const hasAudio = computed(() => !!persona.value?.has_audio);
const initial = computed(() => (name.value || '?').charAt(0).toUpperCase());
</script>

<style scoped>
.persona-chip {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-2) var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  font-size: 13px;
}
.chip-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chip-label {
  font-size: 10px;
  color: var(--vf-text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.chip-name {
  font-weight: 600;
  color: var(--vf-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.chip-status {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
  white-space: nowrap;
}
.chip-status.ok {
  background: var(--vf-ok-soft);
  color: var(--vf-ok);
}
.chip-status.none {
  background: var(--vf-bg-3);
  color: var(--vf-text-3);
}
.is-empty {
  border-style: dashed;
  color: var(--vf-text-3);
  cursor: pointer;
}
.empty-icon { font-size: 18px; }
.empty-text { font-size: 12px; }
</style>
