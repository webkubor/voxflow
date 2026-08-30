/**
 * 克隆合成、音色设计、脚本与剧本任务状态。
 * API：/api/clone、/api/design、/api/scripts、/api/dialogue
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { useTasksStore } from './tasks';

const createCloneForm = () => ({ persona: '', text: '', tone: '', emotion: '', emotionPriority: false });
const createDesignForm = () => ({ name: '', text: '', tone: '', emotion: '', commit: false });

export const useSynthStore = defineStore('synth', () => {
  const cloneForm = reactive(createCloneForm());
  const designForm = reactive(createDesignForm());
  const designPresets = ref([]);
  const savedScripts = ref([]);
  const error = ref('');

  const loadScripts = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/scripts');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '加载脚本失败');
      savedScripts.value = data.scripts || [];
      return savedScripts.value;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const loadScript = (script) => {
    cloneForm.text = script.content || '';
  };

  const saveScript = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/scripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: cloneForm.text.slice(0, 15), content: cloneForm.text }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '保存脚本失败');
      savedScripts.value = data.scripts || [];
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const deleteScript = async (id) => {
    error.value = '';
    try {
      const res = await fetch(`/api/scripts/${encodeURIComponent(id)}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '删除脚本失败');
      savedScripts.value = data.scripts || [];
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const submitTask = async (url, body, loadingText) => {
    const tasks = useTasksStore();
    error.value = '';
    tasks.showLoading(loadingText);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '任务提交失败');
      tasks.taskPanelCollapsed = false;
      tasks.showToast('任务已提交，请在右下角任务队列中关注进度', 'success');
      return data;
    } catch (cause) {
      error.value = cause.message;
      tasks.showToast(cause.message, 'error');
      throw cause;
    } finally {
      tasks.hideLoading();
    }
  };

  const doClone = () => submitTask('/api/clone', {
    persona: cloneForm.persona,
    text: cloneForm.text,
    tone: cloneForm.tone,
    emotion: cloneForm.emotion,
    emotion_priority: cloneForm.emotionPriority,
  }, '正在提交克隆合成任务...');

  const doDesign = () => submitTask('/api/design', {
    voice_name: designForm.name,
    text: designForm.text,
    tone: designForm.tone,
    emotion: designForm.emotion,
    commit: designForm.commit,
  }, '正在提交音色设计任务...');

  const loadDialogueSample = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/scripts');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '载入剧本样例失败');
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const submitDialogue = (form) => submitTask('/api/dialogue', form, '正在提交剧本合成任务...');

  return {
    cloneForm, designForm, designPresets, savedScripts, error,
    loadScripts, loadScript, saveScript, deleteScript, doClone, doDesign, loadDialogueSample, submitDialogue,
  };
});
