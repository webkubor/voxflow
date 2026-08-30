/**
 * 音色库、当前音色与样音试听状态。
 * API：GET /api/personas、POST /api/personas/add、DELETE /api/personas/{key}
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
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
      const data = await api.personas();
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
      const data = await api.deletePersona(key);
      if (selectedPersona.value === key) selectedPersona.value = null;
      await loadPersonas();
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  /**
   * 改名字 / 改描述。
   *
   * 名字跟文件路径已经解耦（后端只从 ref 字段读音频），所以这里就是改两个
   * 字段，不会牵动任何文件 —— 想叫什么叫什么，中文、空格、标点都行。
   */
  const updatePersona = async (key, { name, desc }) => {
    error.value = '';
    try {
      const body = new FormData();
      // 只提交真正要改的字段：desc 允许改成空串（清空描述），
      // 所以判 undefined 不判真值，否则清空这个操作会被吞掉。
      if (name !== undefined) body.append('name', name);
      if (desc !== undefined) body.append('desc', desc);
      const data = await api.updatePersona(key, body);
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
      const data = await api.addPersona(formData);
      await loadPersonas();
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  return {
    personas, selectedPersona, previewKey, previewProgress, previewPlayer, error,
    loadPersonas, selectPersona, togglePreview, onPreviewProgress, onPreviewEnded,
    deletePersona, addPersona, updatePersona,
  };
});
