/**
 * 异步任务队列、全局加载遮罩与消息提示。
 * API：GET /api/tasks、DELETE /api/tasks/{taskId}
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
import { TASKS_POLL_MS, TASKS_POLL_BUSY_MS } from '../config/constants';
import { useLibraryStore } from './library';
import { useVoicesStore } from './voices';

const RUNNING_TASK_STATUSES = new Set(['queued', 'running']);

/** 单个后台任务。形状按 TaskPanel 的消费和本 store 自己读的字段拼的。 */
export interface TaskItem {
  id: string;
  type: string;
  status: string;
  params?: Record<string, unknown>;
  stage?: string;
  created_at?: string;
  error?: string;
  result?: {
    urls?: string[];
    files?: string[];
    committed?: boolean;
  };
}

/** MessageApi.vue 把 useMessage() 挂到 window.$message 上；全局没有类型声明，这里按使用方式窄化。 */
type GlobalMessage = { [key: string]: (content: string) => void };

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<TaskItem[]>([]);
  const taskPanelCollapsed = ref(false);
  const globalLoading = ref(false);
  const globalLoadingText = ref('');
  const error = ref('');
  const previousStatuses = new Map<string, string>();
  let pollTimer: number | null = null;

  const showToast = (content: string, type: 'info' | 'success' | 'warning' | 'error' | 'loading' = 'info') => {
    (window as unknown as { $message?: GlobalMessage }).$message?.[type]?.(content);
  };

  const showLoading = (text: string) => {
    globalLoadingText.value = text;
    globalLoading.value = true;
  };

  const hideLoading = () => {
    globalLoading.value = false;
    globalLoadingText.value = '';
  };

  const handleCompletedTask = async (task: TaskItem) => {
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

  const pollTasks = async (): Promise<void> => {
    error.value = '';
    try {
      const data = await api.tasks();
      // api 层把 tasks 标成 unknown[]，这里按实际消费形状窄化。
      tasks.value = (data.tasks || []) as TaskItem[];
      await Promise.all(tasks.value.map(handleCompletedTask));
      tasks.value.forEach((task) => previousStatuses.set(task.id, task.status));
    } catch (cause) {
      error.value = await toMessage(cause);
    } finally {
      const isBusy = tasks.value.some((task) => RUNNING_TASK_STATUSES.has(task.status));
      pollTimer = window.setTimeout(pollTasks, isBusy ? TASKS_POLL_BUSY_MS : TASKS_POLL_MS);
    }
  };

  const cancelTask = async (taskId: string): Promise<{ ok: boolean }> => {
    error.value = '';
    try {
      const data = await api.cancelTask(taskId);
      await pollTasks();
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
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
