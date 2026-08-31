/**
 * 翻唱历史 store —— 跟踪每一次翻唱提交，从发起任务到完成播放的完整状态。
 *
 * ## 与 library store 的关系
 *
 * library store 列出所有生成的音频文件，但不带语义；
 * 这里专门记「这是哪首热歌的翻唱、用谁的 persona、翻唱的诉求是什么」。
 * SunoTab 翻唱模式下方的列表 / LibraryTab 的「翻唱」过滤都从这里读。
 *
 * ## 数据来源
 *
 * 翻唱提交时 push 一条 status=running 的记录；
 * Suno 任务轮询完成时按 task_id reconcile（status / urls / files）。
 * 上传原曲音频的 sunoCover 任务走同一条轮询路径，自动同步。
 *
 * ## 持久化
 *
 * 当前 session-only。刷新页面就清空 —— 翻唱历史不像草稿那么重要，
 * 真要重做可以再点一次热点榜。要持久化的话加 pinia-plugin-persistedstate。
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';

export type CoverStatus = 'running' | 'done' | 'error' | 'cancelled';

export interface CoverItem {
  id: string;             // task_id
  title: string;
  originalSong: string;
  originalArtist?: string;
  tags: string;
  persona: string;
  hasSourceAudio: boolean;  // 上传了原曲音频 → sunoCover 端点
  urls: string[];
  files: string[];
  status: CoverStatus;
  error?: string;
  createdAt: number;
  completedAt?: number;
}

const MAX_COVERS = 50;

export const useCoverHistoryStore = defineStore('coverHistory', () => {
  const items = ref<CoverItem[]>([]);

  /** 新增一条 running 状态的记录 —— 提交翻唱时调用 */
  const add = (item: CoverItem) => {
    items.value.unshift(item);
    if (items.value.length > MAX_COVERS) {
      items.value = items.value.slice(0, MAX_COVERS);
    }
  };

  /** 按 id 合并更新 —— 任务轮询完成时调用 */
  const update = (id: string, patch: Partial<CoverItem>) => {
    const idx = items.value.findIndex((i) => i.id === id);
    if (idx !== -1) Object.assign(items.value[idx], patch);
  };

  /** 用户主动移除一条（不是删除源文件） */
  const remove = (id: string) => {
    items.value = items.value.filter((i) => i.id !== id);
  };

  /** 清空历史（不影响实际音频文件） */
  const clear = () => {
    items.value = [];
  };

  return { items, add, update, remove, clear };
});
