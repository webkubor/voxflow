/**
 * 模型、Suno、中台与 LLM 能力状态。
 * API：GET /api/capabilities、GET /api/status、GET /api/llm/status、POST /api/llm/*
 */
import { computed, reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
import type { Capability, CapabilitiesResponse } from '../types/api';
import { useSynthStore } from './synth';

/** /api/status 返回里的单个模型下载进度块；api 层把它标成 Record<string, unknown>，这里描述实际形状。 */
interface ModelDownloadState {
  percent?: number;
}

interface ModelStatusEntry {
  ready: boolean;
  downloading: boolean;
  loaded: boolean;
  progress: number;
}

/** /api/llm/status 实际返回还带 base_url/models，api 层的声明只有 available/model/error，这里按使用补齐。 */
interface LlmStatusResponse {
  available: boolean;
  base_url?: string;
  models?: string[];
  model?: string;
  error?: string;
}

interface LlmState {
  available: boolean;
  checking: boolean;
  base_url: string;
  models: string[];
  genPrompt: string;
  genWordCount: number | string;   // AIHelpSection 里 v-model 到 n-input，可能是数字也可能是字符串
  genLoading: boolean;
  polStyle: string;
  polLoading: boolean;
}

/** 顶栏能力标签（MainLayout 消费）。 */
interface CapBadge {
  key: string;
  label: string;
  what: string;
  ready?: boolean;
  detail?: string;
  num?: number;
  // Suno 专项字段：套餐 + 月度总额 + 下次重置日
  // 后端没返回时为 undefined —— UI 优雅降级，不显示对应行
  plan?: string;
  creditsRemaining?: number;
  creditsTotal?: number;
  renewDate?: string;
}

/** /api/capabilities 实际还会返回 museav，契约里只有 tts/suno/studio/llm，这里补上。 */
type CapsState = Partial<Record<'tts' | 'suno' | 'studio' | 'llm' | 'museav', Capability>>;

export const useCapabilitiesStore = defineStore('capabilities', () => {
  const caps = ref<CapsState>({});
  const modelStatus = reactive<{ base: ModelStatusEntry; design: ModelStatusEntry }>({
    base: { ready: false, downloading: false, loaded: false, progress: 0 },
    design: { ready: false, downloading: false, loaded: false, progress: 0 },
  });
  const llm = reactive<LlmState>({
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
   *
   * Suno 那一条更细：有套餐、月度总额、下次重置日 —— 一眼看出
   * 「这个月还能生成多少首」、「什么时候用完」，
   * 不至于月底发现浪费了 1000 credits。
   */
  const capBadges = computed<CapBadge[]>(() => {
    const sunoCaps = caps.value.suno;
    return [
      { key: 'tts', label: '语音', what: caps.value.tts?.model || 'Qwen3-TTS',
        ready: caps.value.tts?.ready, detail: caps.value.tts?.detail },
      {
        key: 'suno', label: '音乐',
        // 显示文本：有总额时「套餐 · 已用/总额」，否则「套餐 · 剩余」
        what: formatSunoBadge(sunoCaps),
        ready: sunoCaps?.ready,
        num: sunoCaps?.credits,
        plan: sunoCaps?.plan,
        creditsRemaining: sunoCaps?.credits,
        creditsTotal: sunoCaps?.credits_total,
        renewDate: sunoCaps?.renew_date,
        detail: sunoCaps?.detail,
      },
      { key: 'museav', label: 'museav', what: caps.value.museav?.identity || '未接',
        ready: caps.value.museav?.ready, detail: caps.value.museav?.detail },
      { key: 'llm', label: '文案', what: caps.value.llm?.model || '未接',
        ready: caps.value.llm?.ready, detail: caps.value.llm?.detail },
    ];
  });

  /** 顶栏 Suno chip 的文案。优先「套餐 · 已用/总额」，降级到「套餐 · 剩余」。 */
  const formatSunoBadge = (s: typeof caps.value.suno): string => {
    if (!s) return 'Suno';
    const plan = s.plan || 'Suno';
    const remaining = s.credits;
    const total = s.credits_total;
    if (remaining !== undefined && total !== undefined && total > 0) {
      const used = total - remaining;
      return `${plan} · ${used}/${total}`;
    }
    if (remaining !== undefined) return `${plan} · ${remaining}`;
    return plan;
  };

  const loadCaps = async (): Promise<CapabilitiesResponse> => {
    error.value = '';
    try {
      const data = await api.capabilities();
      caps.value = data;
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const checkStatus = async (): Promise<Record<string, unknown>> => {
    error.value = '';
    try {
      const data = await api.status();
      Object.assign(modelStatus.base, {
        ready: data.base_model, downloading: data.base_downloading, loaded: data.base_loaded,
        progress: (data.base_progress as ModelDownloadState | undefined)?.percent || 0,
      });
      Object.assign(modelStatus.design, {
        ready: data.design_model, downloading: data.design_downloading, loaded: data.design_loaded,
        progress: (data.design_progress as ModelDownloadState | undefined)?.percent || 0,
      });
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const checkLLM = async (): Promise<LlmStatusResponse> => {
    error.value = '';
    llm.checking = true;
    try {
      // api 层的 llmStatus 返回类型没带 base_url/models，这里按实际响应放宽。
      const data = (await api.llmStatus()) as LlmStatusResponse;
      Object.assign(llm, { available: data.available, base_url: data.base_url || '', models: data.models || [] });
      return data;
    } catch (cause) {
      llm.available = false;
      error.value = await toMessage(cause);
      throw cause;
    } finally {
      llm.checking = false;
    }
  };

  const aiGenerate = async (): Promise<{ text: string }> => {
    llm.genLoading = true;
    error.value = '';
    try {
      const data = await api.aiGenerate(llm.genPrompt);
      useSynthStore().cloneForm.text = data.text || '';
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    } finally {
      llm.genLoading = false;
    }
  };

  const aiPolish = async (): Promise<{ text: string }> => {
    llm.polLoading = true;
    error.value = '';
    try {
      // 原 JS 里 `text` 是未声明变量：一点「润色文案」就 ReferenceError，
      // 什么都没发生。润色对象是声音克隆页的文案框（AIHelpSection 面板提示
      // 「将对下方文本框中的文案进行润色改写」），风格取 llm.polStyle。
      const text = useSynthStore().cloneForm.text;
      if (!text.trim()) throw new Error('请先在文本框输入要润色的文案');
      const data = await api.aiPolish({ text, style: llm.polStyle });
      useSynthStore().cloneForm.text = data.text || '';
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    } finally {
      llm.polLoading = false;
    }
  };

  return { caps, modelStatus, llm, error, capBadges, loadCaps, checkStatus, checkLLM, aiGenerate, aiPolish };
});
