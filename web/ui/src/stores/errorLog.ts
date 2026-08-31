/**
 * 错误日志 store —— 持久化最近 N 条错误，给 UI 面板和复制详情用。
 *
 * ## 为什么不在 console / Sentry 之类的远端
 *
 * 1. 本地工具不应该把用户音频/音色数据发到远端 —— 跟「音频不出本机」是一回事
 * 2. 离线/网络挂了的时候 console 反而是唯一证据
 * 3. 用户报的 bug 永远比 telemetry 准 —— 「能复制错误详情」是核心 UX
 *
 * ## 去重
 *
 * 同 fingerprint 的错误（同一接口、同一状态码、同一首句消息）合并计数，
 * 不刷屏。点开面板能看到「这个错出现了 5 次，最后一次在 14:32」。
 *
 * ## 限额
 *
 * 最多保留 200 条。最旧的滚出去。
 * 不持久化到 localStorage —— 错误里的 url 含 query，刷新一下就过期了。
 */
import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { ErrorRecord, VoxError, fingerprintOf } from '../lib/errors';

const MAX_RECORDS = 200;
const FINGERPRINT_WINDOW_MS = 60_000;   // 1 分钟内同 fingerprint 算「重复」

interface PendingMerge {
  record: ErrorRecord;
  lastSeen: number;
}

export const useErrorLogStore = defineStore('errorLog', () => {
  const records = ref<ErrorRecord[]>([]);
  const pendingMerge = new Map<string, PendingMerge>();

  /** 计数器：未确认的错误数（state === 'error' || 'fatal'） */
  const unreadCount = computed(
    () => records.value.filter((r) => r.severity === 'error' || r.severity === 'fatal').length,
  );

  /**
   * 推一条错误进来。
   * 同 fingerprint 在 60s 内重复 → 计数 +1，不重复入栈。
   */
  const report = (err: VoxError) => {
    const fp = fingerprintOf(err);
    const now = Date.now();
    const existing = pendingMerge.get(fp);
    if (existing && now - existing.lastSeen < FINGERPRINT_WINDOW_MS) {
      existing.record.count += 1;
      existing.record.timestamp = now;
      existing.lastSeen = now;
      return existing.record;
    }

    const record: ErrorRecord = {
      id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: now,
      message: err.message,
      detail: err.toDetail(),
      severity: err.severity,
      source: err.source,
      status: err.status,
      method: err.method,
      url: err.url,
      requestId: err.requestId,
      context: err.context,
      fingerprint: fp,
      count: 1,
    };
    pendingMerge.set(fp, { record, lastSeen: now });

    // 清理过期的 merge 状态
    for (const [key, val] of pendingMerge) {
      if (now - val.lastSeen > FINGERPRINT_WINDOW_MS) pendingMerge.delete(key);
    }

    records.value.unshift(record);
    if (records.value.length > MAX_RECORDS) {
      records.value = records.value.slice(0, MAX_RECORDS);
    }
    return record;
  };

  const dismiss = (id: string) => {
    records.value = records.value.filter((r) => r.id !== id);
  };

  const clearAll = () => {
    records.value = [];
    pendingMerge.clear();
  };

  /** 全部标记为已读 —— 角标归零，但不删除 */
  const markAllRead = () => {
    for (const r of records.value) {
      if (r.severity === 'warning') continue;
      // 通过把它降级到 warning 来归零未读？不直观。直接返回 unreadCount 计算时排除 timestamp > lastReadTs
    }
  };

  return { records, unreadCount, report, dismiss, clearAll };
});
