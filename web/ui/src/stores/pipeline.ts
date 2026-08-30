/**
 * 作品流水线看板状态。
 * API：GET /api/pipeline、POST /api/pipeline/stage、/track、/platform
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
import type { PipelineResponse, PlatformAccount, PlatformKey, Stage, Track } from '../types/api';

/**
 * 所有请求都走 api 层，store 里不出现 fetch。
 *
 * 以前每个 store 自己写一遍拼 URL、判 res.ok、解 JSON、抓错误 —— 25 处，
 * 每处都可能漏一步。漏了判 res.ok 就是拿着 500 的响应当正常数据用。
 */
const guard = async <T>(fn: () => Promise<T>, error: { value: string }): Promise<T> => {
  error.value = '';
  try {
    return await fn();
  } catch (cause) {
    error.value = await toMessage(cause);
    throw cause;
  }
};

export const usePipelineStore = defineStore('pipeline', () => {
  const stages = ref<Stage[]>([]);
  const stageLabels = ref<Record<string, string>>({});
  // 平台是**对象**不是数组 —— 模板里遍历要用 (值, 键)。
  // 上一版按数组遍历，复选框 value 是 undefined，勾了等于没勾。
  const platforms = ref<PipelineResponse['platforms']>({} as PipelineResponse['platforms']);
  const summary = ref<Record<string, number>>({});
  const tracks = ref<Track[]>([]);   // 流水线作品：走到哪一步
  // 云备份台账是另一份数据（同一批歌，但字段是「备份在哪」不是「走到哪步」）。
  // 曾经跟 tracks 共用一个 ref —— 两个接口写同一个字段、结构还不一样，
  // 谁后加载谁把对方覆盖掉，表现为「看板刷新一下内容就变了」。
  const backupTracks = ref<Track[]>([]);
  const publishAccounts = ref<PlatformAccount[]>([]);
  const artist = ref<Record<string, unknown> | null>(null);
  const error = ref('');

  const loadPipeline = async () => {
    const data = await guard(() => api.pipeline(), error);
    stages.value = data.stages || [];
    stageLabels.value = data.stage_labels || {};
    platforms.value = data.platforms || [];
    summary.value = data.summary || {};
    tracks.value = data.tracks || [];
    return data;
  };

  const setStage = (trackId: string, stage: Stage) => guard(() => api.setStage(trackId, stage), error);
  const upsertTrack = (track: Partial<Track> & { track_id: string }) => guard(() => api.upsertTrack(track), error);
  const setPlatformStatus = (p: { track_id: string; platform: PlatformKey; status: string }) => guard(() => api.setPlatformStatus(p), error);
  const loadPublishBoard = async () => {
    const data = await guard(() => api.publishBoard(), error);
    publishAccounts.value = (data.accounts || []) as PlatformAccount[];
    backupTracks.value = data.tracks || [];
    return data;
  };

  const saveArtist = async (updatedArtist: Record<string, unknown>) => {
    const data = await guard(() => api.saveArtist(updatedArtist), error);
    artist.value = data.artist;
    return data;
  };

  return {
    stages, stageLabels, platforms, summary, tracks, backupTracks, publishAccounts, artist, error,
    loadPipeline, loadPublishBoard, setStage, upsertTrack, setPlatformStatus, saveArtist,
  };
});
