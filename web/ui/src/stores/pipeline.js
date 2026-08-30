/**
 * 作品流水线看板状态。
 * API：GET /api/pipeline、POST /api/pipeline/stage、/track、/platform
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';

export const usePipelineStore = defineStore('pipeline', () => {
  const stages = ref([]);
  const stageLabels = ref({});
  const platforms = ref([]);
  const summary = ref({});
  const tracks = ref([]);            // 流水线作品：走到哪一步
  // 云备份台账是另一份数据（同一批歌，但字段是「备份在哪」不是「走到哪步」）。
  // 曾经跟 tracks 共用一个 ref —— 两个接口写同一个字段、结构还不一样，
  // 谁后加载谁把对方覆盖掉，表现为「看板刷新一下内容就变了」。
  const backupTracks = ref([]);
  const publishAccounts = ref([]);
  const error = ref('');

  const request = async (url, method = 'GET', body) => {
    error.value = '';
    try {
      const res = await fetch(url, body === undefined ? { method } : {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || data.detail || '流水线操作失败');
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const loadPipeline = async () => {
    const data = await request('/api/pipeline');
    stages.value = data.stages || [];
    stageLabels.value = data.stage_labels || {};
    platforms.value = data.platforms || [];
    summary.value = data.summary || {};
    tracks.value = data.tracks || [];
    return data;
  };

  const setStage = (trackId, stage) => request('/api/pipeline/stage', 'POST', { track_id: trackId, stage });
  const upsertTrack = (track) => request('/api/pipeline/track', 'POST', track);
  const setPlatformStatus = (platform) => request('/api/pipeline/platform', 'POST', platform);
  const loadPublishBoard = async () => {
    const data = await request('/api/publish-board');
    publishAccounts.value = data.accounts || [];
    backupTracks.value = data.tracks || [];
    return data;
  };

  return {
    stages, stageLabels, platforms, summary, tracks, backupTracks, publishAccounts, error,
    loadPipeline, loadPublishBoard, setStage, upsertTrack, setPlatformStatus,
  };
});
