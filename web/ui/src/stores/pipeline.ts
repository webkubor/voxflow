/**
 * 作品流水线看板状态。
 * API：GET /api/pipeline、POST /api/pipeline/stage、/track、/platform
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import type {
  Album, PipelineResponse, PlatformAccount, PlatformKey, Stage, Track,
} from '../types/api';

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
  const artist = ref(null);
  const error = ref('');

  const request = async <T = any>(url: string, method = 'GET', body?: unknown): Promise<T> => {
    error.value = '';
    try {
      const res = await fetch(url, body === undefined ? { method } : {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || '流水线操作失败');
      return data;
    } catch (cause) {
      error.value = (cause as Error).message;
      throw cause;
    }
  };

  const loadPipeline = async () => {
    const data = await request<PipelineResponse>('/api/pipeline');
    stages.value = data.stages || [];
    stageLabels.value = data.stage_labels || {};
    platforms.value = data.platforms || [];
    summary.value = data.summary || {};
    tracks.value = data.tracks || [];
    return data;
  };

  const setStage = (trackId: string, stage: Stage) => request('/api/pipeline/stage', 'POST', { track_id: trackId, stage });
  const upsertTrack = (track: Partial<Track>) => request('/api/pipeline/track', 'POST', track);
  const setPlatformStatus = (platform: { track_id: string; platform: PlatformKey; status: string }) => request('/api/pipeline/platform', 'POST', platform);
  const loadPublishBoard = async () => {
    const data = await request('/api/publish-board');
    publishAccounts.value = data.accounts || [];
    backupTracks.value = data.tracks || [];
    try {
      const artistData = await request('/api/artist');
      artist.value = artistData;
    } catch (e) {
      console.warn('加载艺人档案失败', e);
    }
    return data;
  };

  const saveArtist = async (updatedArtist) => {
    const data = await request('/api/artist', 'POST', updatedArtist);
    artist.value = data.artist;
    return data;
  };

  return {
    stages, stageLabels, platforms, summary, tracks, backupTracks, publishAccounts, artist, error,
    loadPipeline, loadPublishBoard, setStage, upsertTrack, setPlatformStatus, saveArtist,
  };
});
