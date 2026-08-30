/**
 * 克隆合成、音色设计、脚本与剧本任务状态。
 * API：/api/clone、/api/design、/api/scripts、/api/dialogue
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
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
      const data = await api.scripts();
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
      const data = await api.saveScript({ text: scriptText });
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
      const data = await api.deleteScript(id);
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
      const data = await (url.includes('design') ? api.design(payload) : url.includes('dialogue') ? api.dialogue(payload) : api.clone(payload));
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
      const data = await api.scripts();
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
