/**
 * 异步任务队列、全局加载遮罩与消息提示。
 * API：GET /api/tasks、DELETE /api/tasks/{taskId}
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { useLibraryStore } from './library';
import { useVoicesStore } from './voices';

const RUNNING_TASK_STATUSES = new Set(['queued', 'running']);

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref([]);
  const taskPanelCollapsed = ref(false);
  const globalLoading = ref(false);
  const globalLoadingText = ref('');
  const error = ref('');
  const previousStatuses = new Map();
  let pollTimer = null;

  const showToast = (content, type = 'info') => {
    window.$message?.[type]?.(content);
  };

  const showLoading = (text) => {
    globalLoadingText.value = text;
    globalLoading.value = true;
  };

  const hideLoading = () => {
    globalLoading.value = false;
    globalLoadingText.value = '';
  };

  const handleCompletedTask = async (task) => {
    const becameDone = task.status === 'done' && previousStatuses.get(task.id) !== 'done';
    if (!becameDone) return;
    const library = useLibraryStore();
    const voices = useVoicesStore();
    const urls = task.result?.urls || [];
    const files = task.result?.files || [];
    if (urls.length) library.playAudio(urls[0], files[0]);
    await library.loadAudioList().catch((cause) => { error.value = cause.message; });
    if (task.result?.committed) await voices.loadPersonas().catch((cause) => { error.value = cause.message; });
  };

  const pollTasks = async () => {
    error.value = '';
    try {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || '加载任务队列失败');
      tasks.value = data.tasks || [];
      await Promise.all(tasks.value.map(handleCompletedTask));
      tasks.value.forEach((task) => previousStatuses.set(task.id, task.status));
    } catch (cause) {
      error.value = cause.message;
    } finally {
      const isBusy = tasks.value.some((task) => RUNNING_TASK_STATUSES.has(task.status));
      pollTimer = window.setTimeout(pollTasks, isBusy ? 1500 : 5000);
    }
  };

  const cancelTask = async (taskId) => {
    error.value = '';
    try {
      const res = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || data.detail || '取消任务失败');
      await pollTasks();
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const stopPolling = () => {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = null;
  };

  return {
    tasks, taskPanelCollapsed, globalLoading, globalLoadingText, error,
    showToast, showLoading, hideLoading, pollTasks, cancelTask, stopPolling,
  };
});
