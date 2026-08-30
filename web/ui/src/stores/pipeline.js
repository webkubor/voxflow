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
  const tracks = ref([]);
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
    tracks.value = data.tracks || [];
    return data;
  };

  return {
    stages, stageLabels, platforms, summary, tracks, publishAccounts, error,
    loadPipeline, loadPublishBoard, setStage, upsertTrack, setPlatformStatus,
  };
});
