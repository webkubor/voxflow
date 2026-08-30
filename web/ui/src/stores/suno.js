/**
 * Suno 登录状态与音乐生成表单。
 * API：GET /api/suno/status、POST /api/suno/generate、GET /api/tasks
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { useLibraryStore } from './library';
import { useTasksStore } from './tasks';

export const useSunoStore = defineStore('suno', () => {
  const suno = reactive({
    authenticated: false, credits: 0, total_credits_left: 0, plan: '', personas: {}, submitting: false, error: '',
  });
  const sunoForm = reactive({ title: '', tags: '', lyrics: '', persona: '' });
  const lyricsPrompt = ref('');
  const lyricsGenerating = ref(false);
  const error = ref('');
  let taskTimer = null;

  const loadSunoStatus = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/suno/status');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '加载 Suno 状态失败');
      Object.assign(suno, {
        authenticated: data.authenticated, credits: data.credits, total_credits_left: data.total_credits_left,
        plan: data.plan, personas: data.personas || {},
      });
      return data;
    } catch (cause) {
      suno.error = cause.message;
      error.value = cause.message;
      throw cause;
    }
  };

  const pollSunoTask = async (taskId) => {
    try {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '查询 Suno 任务失败');
      const task = (data.tasks || []).find((item) => item.id === taskId);
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
      suno.error = cause.message;
      error.value = cause.message;
    }
    taskTimer = window.setTimeout(() => pollSunoTask(taskId), 5000);
  };

  const submitSuno = async () => {
    error.value = '';
    suno.error = '';
    suno.submitting = true;
    try {
      const res = await fetch('/api/suno/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sunoForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '提交 Suno 任务失败');
      taskTimer = window.setTimeout(() => pollSunoTask(data.task_id), 3000);
      return data;
    } catch (cause) {
      suno.submitting = false;
      suno.error = cause.message;
      error.value = cause.message;
      throw cause;
    }
  };

  const generateLyrics = async () => {
    error.value = '';
    suno.error = '';
    const prompt = lyricsPrompt.value.trim()
      || [sunoForm.title.trim(), sunoForm.tags.trim()].filter(Boolean).join('，');
    if (!prompt) throw new Error('请填写歌词主题，或先填写歌曲标题和风格标签');

    lyricsGenerating.value = true;
    try {
      const res = await fetch('/api/llm/lyrics', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, style: sunoForm.tags.trim() }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || 'AI 歌词生成失败');
      sunoForm.lyrics = data.text;
      useTasksStore().showToast('歌词已生成，可继续编辑、复制或直接出歌', 'success');
      return data;
    } catch (cause) {
      suno.error = cause.message;
      error.value = cause.message;
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
