/**
 * 异步任务队列、全局加载遮罩、消息提示。
 *
 * ## 三种提示行为
 *
 * 1. **showToast(text, type)** —— 普通消息。warning/error 自动落进错误日志。
 * 2. **reportError(err, context)** —— 收到 caught error，落错误日志 + 弹 toast。
 *    用这个替掉之前散在各处的 `showToast(e.message, 'error')`，堆栈和 URL
 *    才不会丢。
 * 3. **showLoading / hideLoading** —— 全局 spinner。
 *
 * ## toast 时长
 *
 * - info / success：3 秒（参考）
 * - warning：5 秒（用户要看完警告才能动手）
 * - error：8 秒 + 可手动关闭（35 credits 没了那种错，得让人看清楚）
 * - fatal（5xx / 网络挂）：persistent，不自动关
 *
 * Naive UI 的 message 默认 duration 是 3000ms 且不能按 type 区分 —— 接管下来。
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toError } from '../api';
import { TASKS_POLL_MS, TASKS_POLL_BUSY_MS } from '../config/constants';
import { useLibraryStore } from './library';
import { useVoicesStore } from './voices';
import { useErrorLogStore } from './errorLog';
import { LOG_PREFIX, VoxError, ErrorContext } from '../lib/errors';

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

/** Naive UI 全局 message API 的最小化类型 */
type NMessage = {
  info?: (content: string, opts?: object) => unknown;
  success?: (content: string, opts?: object) => unknown;
  warning?: (content: string, opts?: object) => unknown;
  error?: (content: string, opts?: object) => unknown;
  loading?: (content: string, opts?: object) => unknown;
};
type GlobalMessage = { $message?: NMessage; $dialog?: unknown };

/** 错误等级 → toast 显示时长。fatal 不自动关。 */
const TOAST_DURATION = {
  info: 3000,
  success: 3000,
  warning: 5000,
  error: 8000,
  fatal: 0,        // 0 表示不自动关
};

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<TaskItem[]>([]);
  const taskPanelCollapsed = ref(false);
  const globalLoading = ref(false);
  const globalLoadingText = ref('');
  const error = ref('');
  const previousStatuses = new Map<string, string>();
  let pollTimer: number | null = null;

  const getMsg = (): NMessage | undefined =>
    (window as unknown as GlobalMessage).$message;

  /**
   * 单纯消息提示。warning/error 自动落错误日志（按当前请求的 action）。
   */
  const showToast = (
    content: string,
    type: 'info' | 'success' | 'warning' | 'error' = 'info',
  ) => {
    const m = getMsg();
    if (!m) return;
    const fn = m[type];
    if (!fn) return;
    fn(content, { duration: TOAST_DURATION[type] });

    if (type === 'error' || type === 'warning') {
      // 字符串来源的轻量错误：没有 HTTP 上下文，只记一句话
      const log = useErrorLogStore();
      log.report(new VoxError({
        message: content,
        source: 'validation',
        severity: type,
        context: { action: 'toast' },
      }));
    }
  };

  /**
   * 收到 caught error 的标准入口。
   *
   * 落错误日志（带 URL / 方法 / 状态码 / 堆栈）+ 弹可关闭的 toast。
   * 不再让 `e.message` 一笔带过 —— 之前那种 toast 闪一下就忘了。
   */
  const reportError = async (err: unknown, context: ErrorContext): Promise<VoxError> => {
    const vox = await toError(err, context);
    const log = useErrorLogStore();
    log.report(vox);

    console.error(`${LOG_PREFIX} ${context.action}`, vox);

    const m = getMsg();
    if (m?.error) {
      m.error(vox.message, {
        duration: TOAST_DURATION[vox.severity],
        closable: true,
        keepAliveOnHover: true,
      });
    }
    return vox;
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
    await library.loadAudioList().catch((cause) => {
      error.value = cause instanceof Error ? cause.message : String(cause);
    });
    if (task.result?.committed) await voices.loadPersonas().catch((cause) => {
      error.value = cause instanceof Error ? cause.message : String(cause);
    });
  };

  const pollTasks = async (): Promise<void> => {
    error.value = '';
    try {
      const data = await api.tasks();
      tasks.value = (data.tasks || []) as TaskItem[];
      await Promise.all(tasks.value.map(handleCompletedTask));
      tasks.value.forEach((task) => previousStatuses.set(task.id, task.status));
    } catch (cause) {
      error.value = (await toError(cause, { action: 'tasks.poll' })).message;
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
      throw await reportError(cause, { action: 'tasks.cancel', tags: { taskId } });
    }
  };

  const stopPolling = () => {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = null;
  };

  return {
    tasks, taskPanelCollapsed, globalLoading, globalLoadingText, error,
    showToast, reportError, showLoading, hideLoading, pollTasks, cancelTask, stopPolling,
  };
});
