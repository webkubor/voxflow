/**
 * 模型、Suno、中台与 LLM 能力状态。
 * API：GET /api/capabilities、GET /api/status、GET /api/llm/status、POST /api/llm/*
 */
import { computed, reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
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

  /**
   * 顶栏能力标签。
   *
   * 每个标签直接写出「这项能力当前用的是什么」，不是只亮一个绿点 ——
   * 四个绿灯长得一模一样，人看不出哪个是哪个，也不知道跑的是哪个模型。
   * `what` 就是那个具体值（模型名 / 租户名），`detail` 留给悬停看全貌。
   */
  const capBadges = computed(() => [
    { key: 'tts', label: '语音', what: caps.value.tts?.model || 'Qwen3-TTS',
      ready: caps.value.tts?.ready, detail: caps.value.tts?.detail },
    { key: 'suno', label: '音乐', what: caps.value.suno?.model || 'Suno',
      ready: caps.value.suno?.ready, num: caps.value.suno?.credits, detail: caps.value.suno?.detail },
    { key: 'museav', label: 'museav', what: caps.value.museav?.identity || '未接',
      ready: caps.value.museav?.ready, detail: caps.value.museav?.detail },
    { key: 'llm', label: '文案', what: caps.value.llm?.model || '未接',
      ready: caps.value.llm?.ready, detail: caps.value.llm?.detail },
  ]);

  const loadCaps = async () => {
    error.value = '';
    try {
      const data = await api.capabilities();
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
      const data = await api.status();
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
      const data = await api.llmStatus();
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
      const data = await api.aiGenerate(llm.genPrompt);
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
      const data = await api.aiPolish(text);
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
