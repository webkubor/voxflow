/**
 * 模型、Suno、中台与 LLM 能力状态。
 * API：GET /api/capabilities、GET /api/status、GET /api/llm/status、POST /api/llm/*
 */
import { computed, reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { useSynthStore } from './synth';

export const useCapabilitiesStore = defineStore('capabilities', () => {
  const caps = ref({});
  const modelStatus = reactive({
    base: { ready: false, downloading: false, loaded: false, progress: 0 },
    design: { ready: false, downloading: false, loaded: false, progress: 0 },
  });
  const llm = reactive({
    available: false, checking: false, base_url: '', models: [], genPrompt: '', genWordCount: 100,
    genLoading: false, polStyle: '', polLoading: false,
  });
  const error = ref('');

  const capBadges = computed(() => [
    { key: 'tts', label: '语音', ready: caps.value.tts?.ready, detail: caps.value.tts?.detail },
    { key: 'suno', label: 'Suno', ready: caps.value.suno?.ready, num: caps.value.suno?.credits, detail: caps.value.suno?.detail },
    { key: 'studio', label: '中台', ready: caps.value.studio?.ready, detail: caps.value.studio?.detail },
    { key: 'llm', label: '文案', ready: caps.value.llm?.ready, detail: caps.value.llm?.detail },
  ]);

  const loadCaps = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/capabilities');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '加载能力状态失败');
      caps.value = data;
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const checkStatus = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '加载模型状态失败');
      Object.assign(modelStatus.base, {
        ready: data.base_model, downloading: data.base_downloading, loaded: data.base_loaded,
        progress: data.base_progress?.percent || 0,
      });
      Object.assign(modelStatus.design, {
        ready: data.design_model, downloading: data.design_downloading, loaded: data.design_loaded,
        progress: data.design_progress?.percent || 0,
      });
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const checkLLM = async () => {
    error.value = '';
    llm.checking = true;
    try {
      const res = await fetch('/api/llm/status');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '检查文案助手连接失败');
      Object.assign(llm, { available: data.available, base_url: data.base_url || '', models: data.models || [] });
      return data;
    } catch (cause) {
      llm.available = false;
      error.value = cause.message;
      throw cause;
    } finally {
      llm.checking = false;
    }
  };

  const aiGenerate = async () => {
    llm.genLoading = true;
    error.value = '';
    try {
      const res = await fetch('/api/llm/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: llm.genPrompt, word_count: parseInt(llm.genWordCount, 10) || 100 }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '生成文案失败');
      useSynthStore().cloneForm.text = data.text || '';
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    } finally {
      llm.genLoading = false;
    }
  };

  const aiPolish = async () => {
    llm.polLoading = true;
    error.value = '';
    try {
      const res = await fetch('/api/llm/polish', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: useSynthStore().cloneForm.text, style: llm.polStyle || '自然有亲和力' }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '润色文案失败');
      useSynthStore().cloneForm.text = data.text || '';
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    } finally {
      llm.polLoading = false;
    }
  };

  return { caps, modelStatus, llm, error, capBadges, loadCaps, checkStatus, checkLLM, aiGenerate, aiPolish };
});
