/**
 * 音色库、当前音色与样音试听状态。
 * API：GET /api/personas、POST /api/personas/add、DELETE /api/personas/{key}
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
import type { Persona, PersonasResponse } from '../types/api';
import { useSynthStore } from './synth';
import type { DesignPreset } from './synth';

export const useVoicesStore = defineStore('voices', () => {
  const personas = ref<Record<string, Persona>>({});
  const selectedPersona = ref<string | null>(null);
  const previewKey = ref<string | null>(null);
  const previewProgress = ref(0);
  const previewPlayer = ref<HTMLAudioElement | null>(null);
  const error = ref('');

  const loadPersonas = async (): Promise<PersonasResponse> => {
    error.value = '';
    try {
      const data = await api.personas();
      personas.value = data.personas || {};
      // 契约里 presets 是 unknown[]；实际形状是 DesignTab 消费的
      // {voice_name, tone, text, emotion}（定义在 synth store），这里窄化后写入。
      useSynthStore().designPresets = (data.presets || []) as DesignPreset[];
      if (!selectedPersona.value) {
        const [firstKey] = Object.keys(personas.value);
        if (firstKey) selectPersona(firstKey);
      }
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const selectPersona = (key: string) => {
    selectedPersona.value = key;
    const persona = personas.value[key];
    if (persona) {
      const synth = useSynthStore();
      synth.cloneForm.persona = key;
      synth.cloneForm.tone = persona.instruction || '';
    }
  };

  const togglePreview = (key: string) => {
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

  const deletePersona = async (key: string): Promise<{ ok: boolean }> => {
    error.value = '';
    try {
      const data = await api.deletePersona(key);
      if (selectedPersona.value === key) selectedPersona.value = null;
      await loadPersonas();
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  /**
   * 改名字 / 改描述。
   *
   * 名字跟文件路径已经解耦（后端只从 ref 字段读音频），所以这里就是改两个
   * 字段，不会牵动任何文件 —— 想叫什么叫什么，中文、空格、标点都行。
   */
  const updatePersona = async (
    key: string,
    { name, desc }: { name?: string; desc?: string },
  ): Promise<{ ok: boolean; name: string; desc: string }> => {
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
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const addPersona = async (formData: FormData): Promise<{ ok: boolean; key: string }> => {
    error.value = '';
    try {
      const data = await api.addPersona(formData);
      await loadPersonas();
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  return {
    personas, selectedPersona, previewKey, previewProgress, previewPlayer, error,
    loadPersonas, selectPersona, togglePreview, onPreviewProgress, onPreviewEnded,
    deletePersona, addPersona, updatePersona,
  };
});
