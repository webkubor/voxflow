/**
 * Suno 登录状态与音乐生成表单。
 * API：GET /api/suno/status、POST /api/suno/generate、GET /api/tasks
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
import { useLibraryStore } from './library';
import { useTasksStore } from './tasks';
import type { TaskItem } from './tasks';

interface SunoState {
  authenticated: boolean;
  credits: number;
  total_credits_left: number;
  plan: string;
  personas: Record<string, string>;
  submitting: boolean;
  error: string;
}

interface SunoFormState {
  title: string;
  tags: string;
  lyrics: string;
  persona: string;
}

export const useSunoStore = defineStore('suno', () => {
  const suno = reactive<SunoState>({
    authenticated: false, credits: 0, total_credits_left: 0, plan: '', personas: {}, submitting: false, error: '',
  });
  const sunoForm = reactive<SunoFormState>({ title: '', tags: '', lyrics: '', persona: '' });
  const lyricsPrompt = ref('');
  const lyricsGenerating = ref(false);
  const error = ref('');
  let taskTimer: number | null = null;

  const loadSunoStatus = async (): Promise<Record<string, unknown>> => {
    error.value = '';
    try {
      const data = await api.sunoStatus();
      Object.assign(suno, {
        authenticated: data.authenticated, credits: data.credits, total_credits_left: data.total_credits_left,
        plan: data.plan, personas: data.personas || {},
      });
      return data;
    } catch (cause) {
      const msg = await toMessage(cause);
      suno.error = msg;
      error.value = msg;
      throw cause;
    }
  };

  const pollSunoTask = async (taskId: string): Promise<void> => {
    try {
      const data = await api.tasks();
      // api 层把 tasks 标成 unknown[]，这里按任务形状窄化后按 id 查找。
      const task = ((data.tasks || []) as TaskItem[]).find((item) => item.id === taskId);
      if (!task) return;
      if (task.status === 'done') {
        suno.submitting = false;
        useTasksStore().showToast('🎵 Suno 音乐生成完成！', 'success');
        await useLibraryStore().loadAudioList();
        if (task.result?.urls?.length) useLibraryStore().playAudio(task.result.urls[0], task.result.files?.[0]);
        return;
      }
      if (task.status === 'error') {
        suno.submitting = false;
        suno.error = task.error || '生成失败';
        return;
      }
    } catch (cause) {
      const msg = await toMessage(cause);
      suno.error = msg;
      error.value = msg;
    }
    taskTimer = window.setTimeout(() => pollSunoTask(taskId), 5000);
  };

  const submitSuno = async (): Promise<{ task_id: string }> => {
    error.value = '';
    suno.error = '';
    suno.submitting = true;
    try {
      // 原 JS 里 `payload` 是未声明变量：一点「生成音乐」就 ReferenceError。
      // 后端 SunoGenerateRequest 要 {title, tags, lyrics, persona}。
      const data = await api.sunoGenerate({
        title: sunoForm.title,
        tags: sunoForm.tags,
        lyrics: sunoForm.lyrics,
        persona: sunoForm.persona,
      });
      taskTimer = window.setTimeout(() => pollSunoTask(data.task_id), 3000);
      return data;
    } catch (cause) {
      suno.submitting = false;
      const msg = await toMessage(cause);
      suno.error = msg;
      error.value = msg;
      throw cause;
    }
  };

  const generateLyrics = async (): Promise<{ text: string; lyrics?: string }> => {
    error.value = '';
    suno.error = '';
    const prompt = lyricsPrompt.value.trim()
      || [sunoForm.title.trim(), sunoForm.tags.trim()].filter(Boolean).join('，');
    if (!prompt) throw new Error('请填写歌词主题，或先填写歌曲标题和风格标签');

    lyricsGenerating.value = true;
    try {
      // 原 JS 里 `payload` 是未声明变量：一点「AI 生成歌词」就 ReferenceError。
      // 后端 LLMLyricsRequest 要 {prompt, style}，style 用风格标签。
      const data = await api.aiLyrics({ prompt, style: sunoForm.tags });
      sunoForm.lyrics = data.text;
      useTasksStore().showToast('歌词已生成，可继续编辑、复制或直接出歌', 'success');
      return data;
    } catch (cause) {
      const msg = await toMessage(cause);
      suno.error = msg;
      error.value = msg;
      throw cause;
    } finally {
      lyricsGenerating.value = false;
    }
  };

  const stopPolling = () => {
    if (taskTimer) window.clearTimeout(taskTimer);
    taskTimer = null;
  };

  return {
    suno, sunoForm, lyricsPrompt, lyricsGenerating, error,
    loadSunoStatus, submitSuno, generateLyrics, stopPolling,
  };
});
