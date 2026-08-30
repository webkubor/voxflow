/**
 * 音色库、当前音色与样音试听状态。
 * API：GET /api/personas、POST /api/personas/add、DELETE /api/personas/{key}
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { useSynthStore } from './synth';

export const useVoicesStore = defineStore('voices', () => {
  const personas = ref({});
  const selectedPersona = ref(null);
  const previewKey = ref(null);
  const previewProgress = ref(0);
  const previewPlayer = ref(null);
  const error = ref('');

  const loadPersonas = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/personas');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '加载音色库失败');
      personas.value = data.personas || {};
      useSynthStore().designPresets = data.presets || [];
      if (!selectedPersona.value) {
        const [firstKey] = Object.keys(personas.value);
        if (firstKey) selectPersona(firstKey);
      }
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const selectPersona = (key) => {
    selectedPersona.value = key;
    const persona = personas.value[key];
    if (persona) {
      const synth = useSynthStore();
      synth.cloneForm.persona = key;
      synth.cloneForm.tone = persona.instruction || '';
    }
  };

  const togglePreview = (key) => {
    const audio = previewPlayer.value;
    if (!audio) return;
    if (previewKey.value === key) {
      audio.pause();
      previewKey.value = null;
      return;
    }
    previewKey.value = key;
    previewProgress.value = 0;
    audio.src = `/api/persona-audio?key=${encodeURIComponent(key)}`;
    audio.play().catch((cause) => { error.value = cause.message; });
  };

  const onPreviewProgress = () => {
    const audio = previewPlayer.value;
    if (audio?.duration) previewProgress.value = (audio.currentTime / audio.duration) * 100;
  };

  const onPreviewEnded = () => {
    previewKey.value = null;
    previewProgress.value = 0;
  };

  const deletePersona = async (key) => {
    error.value = '';
    try {
      const res = await fetch(`/api/personas/${encodeURIComponent(key)}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '删除音色失败');
      if (selectedPersona.value === key) selectedPersona.value = null;
      await loadPersonas();
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const addPersona = async (formData) => {
    error.value = '';
    try {
      const res = await fetch('/api/personas/add', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '添加音色失败');
      await loadPersonas();
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  return {
    personas, selectedPersona, previewKey, previewProgress, previewPlayer, error,
    loadPersonas, selectPersona, togglePreview, onPreviewProgress, onPreviewEnded, deletePersona, addPersona,
  };
});
