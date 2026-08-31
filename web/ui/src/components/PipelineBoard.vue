<template>
  <div class="board-wrap">
    <header class="board-head">
      <h3 class="board-title">
        <Icon name="board" size="md" />
        <span>作品流水线</span>
      </h3>
      <div class="board-tools">
        <button class="ghost-btn" @click="openInbox">
          <Icon name="upload" size="sm" />
          <span>从下载导入</span>
        </button>
        <button class="ghost-btn" @click="load">
          <Icon name="refresh" size="sm" />
          <span>刷新</span>
        </button>
      </div>
    </header>

    <!-- 计数条 -->
    <div class="counters">
      <div v-for="c in counters" :key="c.key" class="counter" :class="{ 'is-zero': !c.n, 'is-current': c.key === currentStageKey }">
        <span class="counter-n">{{ c.n }}</span>
        <span class="counter-label">{{ c.label }}</span>
      </div>
    </div>

    <n-alert v-if="error" type="error" :show-icon="false" class="board-err">{{ error }}</n-alert>

    <n-empty
      v-if="!tracks.length"
      description="还没有作品"
      class="board-empty"
    >
      <template #extra>
        <p class="empty-hint">去「AI 音乐」出一首，会自动登记到这里。</p>
        <button class="ghost-btn" @click="openInbox">
          <Icon name="upload" size="sm" />
          <span>或从下载目录导入</span>
        </button>
      </template>
    </n-empty>

    <div v-else class="track-list">
      <!-- 批量工具条 -->
      <div v-if="selectedIds.size" class="batch-bar">
        <span class="batch-count">已选 {{ selectedIds.size }} 首</span>
        <button class="ghost-btn small" @click="selectedIds = new Set()">取消选择</button>
        <button class="primary-btn small" :disabled="batchBusy" @click="batchAdvance">
          {{ batchBusy ? '推进中…' : '批量推进到下一步' }}
        </button>
        <span class="batch-hint">发版那步（selected → publishing）需单独选平台</span>
      </div>

      <article v-for="t in tracks" :key="t.id" class="track">
        <div class="track-head">
          <!-- 批量勾选 -->
          <label v-if="canBatchAdvance(t)" class="track-check" :title="`勾选「${t.title}」`">
            <input
              type="checkbox"
              :checked="selectedIds.has(t.id)"
              @change="toggleSelect(t.id)"
            />
          </label>
          <div v-else class="track-check-spacer"></div>

          <!-- 封面 -->
          <img v-if="t.cover_url" :src="t.cover_url" class="track-cover" :alt="t.title" />
          <div v-else class="track-cover track-cover-empty">♪</div>

          <div class="track-main">
            <div class="track-title-row">
              <span class="track-title">{{ t.title }}</span>
              <span class="stage-pill" :class="`stage-${t.stage}`">{{ t.stage_label }}</span>
            </div>
            <p v-if="t.album_desc" class="track-desc">{{ t.album_desc }}</p>

            <!-- n-steps 进度：圆点 + 文字 label，比纯圆点好懂 -->
            <div class="steps">
              <template v-for="(s, i) in stages" :key="s">
                <div class="step" :class="stepClass(t.stage, s, i)">
                  <span class="step-dot">
                    <Icon v-if="i < stageIndex(t.stage)" name="check" size="sm" />
                  </span>
                  <span class="step-label">{{ stageLabels[s] }}</span>
                </div>
                <div v-if="i < stages.length - 1" class="step-line" :class="{ done: i < stageIndex(t.stage) }"></div>
              </template>
            </div>

            <audio v-if="t.audio_url" :src="t.audio_url" controls preload="none" class="track-audio" />
          </div>
        </div>

        <div class="track-foot">
          <div class="track-tags">
            <span v-if="t.voice" class="meta-pill">🎙️ {{ t.voice }}</span>
            <span
              v-for="(info, pk) in t.platforms"
              :key="pk"
              class="meta-pill warn"
            >
              {{ platformLabel(pk) }} · {{ statusLabel(info.status) }}
            </span>
          </div>
          <div class="track-actions">
            <button
              v-if="t.lyrics || Object.keys(t.platforms || {}).length"
              class="ghost-btn small"
              @click="toggleExpand(t.id)"
            >
              <Icon :name="expanded.has(t.id) ? 'chevron-up' : 'chevron-down'" size="sm" />
              <span>{{ expanded.has(t.id) ? '收起' : '详情' }}</span>
            </button>
            <button
              v-if="nextAction(t)"
              class="primary-btn small"
              :class="`action-${nextAction(t).type}`"
              :disabled="busyId === t.id"
              @click="advance(t)"
            >
              <Icon name="arrow-right" size="sm" />
              <span>{{ nextAction(t).label }}</span>
            </button>
          </div>
        </div>

        <!-- 详情：歌词和发布配置 -->
        <div v-if="expanded.has(t.id)" class="track-detail">
          <div v-if="t.tags" class="detail-block">
            <span class="detail-label">风格</span>
            <span class="detail-tags">{{ t.tags }}</span>
          </div>
          <div v-if="t.lyrics" class="detail-block">
            <span class="detail-label">歌词</span>
            <pre class="detail-lyrics">{{ t.lyrics }}</pre>
          </div>
          <div v-for="(info, pk) in t.platforms" :key="pk" class="detail-block">
            <span class="detail-label">{{ platformLabel(pk) }}</span>
            <div class="detail-platform">
              <span class="meta-pill warn">{{ statusLabel(info.status) }}</span>
              <span v-if="info.submitted_at" class="detail-meta">提交于 {{ info.submitted_at.replace('T', ' ') }}</span>
              <p v-if="info.note" class="detail-meta">{{ info.note }}</p>
              <div v-if="info.config" class="detail-config">
                <template v-for="(v, k) in info.config" :key="k">
                  <div v-if="!k.startsWith('_') && typeof v !== 'object'" class="config-row">
                    <span class="config-k">{{ k }}</span><span class="config-v">{{ v }}</span>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>

    <!-- 确认发版弹窗 -->
    <n-modal v-model:show="showPublish" preset="card" title="确认发版" style="max-width: 460px">
      <p class="modal-lead">
        <strong>{{ publishTrack?.title }}</strong> 要发到哪些平台？
      </p>
      <p class="modal-hint">各平台要求不同，选定后才能按对应 SOP 生成封面和文案。</p>

      <div class="platform-picks">
        <label v-for="(p, pk) in platforms" :key="pk" class="platform-pick">
          <input type="checkbox" :value="pk" v-model="pickedPlatforms" />
          <span class="pick-label">{{ p.label }}</span>
          <span class="pick-meta">封面 {{ p.cover }} · {{ p.ai_field }}</span>
        </label>
      </div>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showPublish = false">取消</n-button>
          <n-button type="primary" :loading="!!busyId" @click="confirmPublish">确认发版</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 导入下载目录 -->
    <n-modal v-model:show="showInbox" preset="card" title="从下载目录导入" style="max-width: 560px">
      <p class="modal-hint">
        Suno 下载的音频进 Downloads 后不会自动入库。挑要收的，工具复制进音乐库并登记为「已出歌」（原文件不动，重名自动加后缀）。
      </p>
      <n-spin :show="inboxLoading">
        <n-empty v-if="!inboxLoading && !inboxFiles.length" description="最近一周没有可导入的音频" />
        <div v-else class="inbox-list">
          <label v-for="f in inboxFiles" :key="f.path" class="inbox-item">
            <input
              type="checkbox"
              :value="f.path"
              v-model="pickedFiles"
              :disabled="f.in_library"
            />
            <span class="inbox-name" :title="f.path">{{ f.name }}</span>
            <span class="inbox-meta">
              {{ f.size_mb }} MB
              <span v-if="f.in_library" class="meta-pill success">已在库</span>
            </span>
          </label>
        </div>
      </n-spin>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showInbox = false">取消</n-button>
          <n-button
            type="primary"
            :loading="inboxImporting"
            :disabled="!pickedFiles.length"
            @click="doInboxImport"
          >
            导入选中（{{ pickedFiles.length }}）
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
/**
 * 作品流水线看板。
 *
 * ## 进度可视化升级
 *
 * 之前 5 个步骤只画圆点 + tooltip，扫一眼看不出「走到哪」。
 * 改成 n-steps 风格：圆点 + 文字 label + 连接线，已完成的打勾，
 * 当前的脉冲高亮。让看板一眼说人话。
 *
 * ## 「当前阶段」计数高亮
 *
 * 计数条里数字最多的那一列才值得关注 —— 那是流水线堵的地方。
 * 其他阶段都是上下文，给个 muted 就行。
 */
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { api, toMessage } from '../api';
import { usePipelineStore } from '../stores/pipeline';
import { useTasksStore } from '../stores/tasks';
import Icon from './Icon.vue';

const pipelineStore = usePipelineStore();
const tasksStore = useTasksStore();
const { stages, stageLabels, platforms, summary, tracks, error } = storeToRefs(pipelineStore);

const busyId = ref('');
const expanded = ref(new Set());
const toggleExpand = (id) => {
  const n = new Set(expanded.value);
  n.has(id) ? n.delete(id) : n.add(id);
  expanded.value = n;
};

const showPublish = ref(false);
const publishTrack = ref(null);
const pickedPlatforms = ref([]);

const load = async () => {
  try {
    await pipelineStore.loadPipeline();
  } catch (cause) {
    tasksStore.showToast(cause.message || '加载流水线失败', 'error');
  }
};
onMounted(load);
defineExpose({ load });

// 下载目录导入
const showInbox = ref(false);
const inboxFiles = ref([]);
const inboxLoading = ref(false);
const inboxImporting = ref(false);
const pickedFiles = ref([]);

const openInbox = async () => {
  showInbox.value = true;
  pickedFiles.value = [];
  inboxLoading.value = true;
  try {
    const data = await api.inbox();
    inboxFiles.value = data.files || [];
  } catch (cause) {
    tasksStore.showToast(await toMessage(cause), 'error');
  } finally {
    inboxLoading.value = false;
  }
};

const doInboxImport = async () => {
  if (!pickedFiles.value.length) {
    tasksStore.showToast('先勾选要导入的文件', 'warning');
    return;
  }
  inboxImporting.value = true;
  try {
    const data = await api.inboxImport(pickedFiles.value);
    tasksStore.showToast(`已导入 ${data.count} 个文件到「已出歌」`, 'success');
    showInbox.value = false;
    await load();
  } catch (cause) {
    tasksStore.showToast(await toMessage(cause), 'error');
  } finally {
    inboxImporting.value = false;
  }
};

const counters = computed(() =>
  stages.value.map((s) => ({ key: s, label: stageLabels.value[s] || s, n: summary.value[s] || 0 })),
);

/** 找出作品数最多的阶段 —— 那是流水线堵的地方 */
const currentStageKey = computed(() => {
  let maxN = 0;
  let maxKey = '';
  for (const c of counters.value) {
    if (c.n > maxN) { maxN = c.n; maxKey = c.key; }
  }
  return maxKey;
});

const stageIndex = (s) => stages.value.indexOf(s);

const stepClass = (currentStage, stage, index) => {
  const ci = stageIndex(currentStage);
  if (index < ci) return 'done';
  if (index === ci) return 'current';
  return 'pending';
};

const nextAction = (track) => {
  switch (track.stage) {
    case 'draft':      return { label: '标记已出歌', to: 'generated', type: 'default' };
    case 'generated':  return { label: '选定这首', to: 'selected', type: 'primary' };
    case 'selected':   return { label: '确认发版', to: 'publishing', type: 'primary', needsPlatform: true };
    case 'publishing': return { label: '标记已上架', to: 'published', type: 'success' };
    default:           return null;
  }
};

const advance = async (track) => {
  const action = nextAction(track);
  if (!action) return;
  if (action.needsPlatform) {
    publishTrack.value = track;
    pickedPlatforms.value = [];
    showPublish.value = true;
    return;
  }
  busyId.value = track.id;
  try {
    await pipelineStore.setStage(track.id, action.to);
    await load();
    tasksStore.showToast(`「${track.title}」→ ${stageLabels.value[action.to]}`, 'success');
  } catch (cause) {
    tasksStore.showToast(cause.message || '操作失败', 'error');
  } finally {
    busyId.value = '';
  }
};

const confirmPublish = async () => {
  if (!pickedPlatforms.value.length) {
    tasksStore.showToast('先选一个要发的平台', 'warning');
    return;
  }
  const track = publishTrack.value;
  busyId.value = track.id;
  try {
    for (const p of pickedPlatforms.value) {
      await pipelineStore.setPlatformStatus({ track_id: track.id, platform: p, status: 'preparing' });
    }
    await pipelineStore.setStage(track.id, 'publishing');
    await load();
    showPublish.value = false;
    tasksStore.showToast(`「${track.title}」进入发版流程`, 'success');
  } catch (cause) {
    tasksStore.showToast(cause.message || '发版失败', 'error');
  } finally {
    busyId.value = '';
  }
};

// 批量操作
const selectedIds = ref(new Set());
const batchBusy = ref(false);

const toggleSelect = (id) => {
  const n = new Set(selectedIds.value);
  n.has(id) ? n.delete(id) : n.add(id);
  selectedIds.value = n;
};

const canBatchAdvance = (t) => {
  const action = nextAction(t);
  return !!action && !action.needsPlatform;
};

const batchAdvance = async () => {
  const targets = tracks.value.filter((t) => selectedIds.value.has(t.id) && canBatchAdvance(t));
  if (!targets.length) {
    tasksStore.showToast('勾选的作品里没有可批量推进的（发版那步需单独选平台）', 'warning');
    return;
  }
  batchBusy.value = true;
  let okCount = 0;
  const failed = [];
  for (const t of targets) {
    const action = nextAction(t);
    try {
      await pipelineStore.setStage(t.id, action.to);
      okCount += 1;
    } catch {
      failed.push(t.title);
    }
  }
  batchBusy.value = false;
  selectedIds.value = new Set();
  await load();
  if (failed.length) {
    tasksStore.showToast(`推进 ${okCount} 首；失败 ${failed.length} 首（${failed.slice(0, 3).join('、')}…）`, 'warning');
  } else {
    tasksStore.showToast(`已批量推进 ${okCount} 首`, 'success');
  }
};

const platformLabel = (key) => platforms.value?.[key]?.label || key;

const PLATFORM_STATUS = {
  preparing: '备料中',
  uploaded: '已上传',
  reviewing: '审核中',
  online: '已上架',
  rejected: '被驳回',
};
const statusLabel = (s) => PLATFORM_STATUS[s] || s;
</script>

<style scoped>
.board-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
  padding: 0 var(--vf-space-2);
  max-width: 1080px;
  margin: 0 auto;
  width: 100%;
}

/* head */
.board-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.board-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.board-tools { display: flex; gap: var(--vf-space-2); }

/* counters */
.counters {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--vf-space-2);
}
.counter {
  padding: var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  text-align: center;
  transition: all 0.15s var(--vf-ease);
}
.counter.is-zero { opacity: 0.4; }
.counter.is-current {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
}
.counter-n {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: var(--vf-primary);
  font-variant-numeric: tabular-nums;
}
.counter-label { font-size: 11px; color: var(--vf-text-3); margin-top: 2px; }

.board-err { margin-bottom: var(--vf-space-3); }

/* empty */
.board-empty { padding: var(--vf-space-8) 0; }
.empty-hint { font-size: 12px; color: var(--vf-text-3); margin: 0 0 var(--vf-space-3); }

/* track */
.track-list { display: flex; flex-direction: column; gap: var(--vf-space-3); }
.track {
  padding: var(--vf-space-4);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
}
.batch-bar {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  border: 1px dashed var(--vf-primary);
  border-radius: var(--vf-radius-md);
  background: var(--vf-primary-soft);
  flex-wrap: wrap;
}
.batch-count { font-weight: 600; color: var(--vf-primary); }
.batch-hint { margin-left: auto; font-size: 11px; color: var(--vf-text-3); }

.track-check {
  display: flex;
  align-items: flex-start;
  padding-top: 22px;
  cursor: pointer;
  flex: none;
}
.track-check input {
  width: 16px;
  height: 16px;
  accent-color: var(--vf-primary);
  cursor: pointer;
}
.track-check-spacer { width: 16px; flex: none; padding-top: 22px; }

.track-head { display: flex; gap: var(--vf-space-3); align-items: flex-start; }
.track-cover {
  width: 64px; height: 64px;
  border-radius: var(--vf-radius-md);
  object-fit: cover;
  background: var(--vf-bg-3);
  flex: none;
}
.track-cover-empty {
  display: flex; align-items: center; justify-content: center;
  color: var(--vf-text-3); font-size: 22px;
}
.track-main { flex: 1; min-width: 0; }
.track-title-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-1);
  flex-wrap: wrap;
}
.track-title {
  font-weight: 600;
  color: var(--vf-text-1);
  font-size: 14px;
}
.stage-pill {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
}
.stage-pill.stage-generated { background: var(--vf-primary-soft); color: var(--vf-primary); }
.stage-pill.stage-selected { background: rgba(95, 125, 149, 0.15); color: var(--vf-info); }
.stage-pill.stage-publishing { background: var(--vf-warn-soft); color: var(--vf-warn); }
.stage-pill.stage-published { background: var(--vf-ok-soft); color: var(--vf-ok); }

.track-desc {
  margin: 0 0 var(--vf-space-2);
  font-size: 12px; line-height: 1.6;
  color: var(--vf-text-2);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.track-audio { width: 100%; height: 30px; margin-top: var(--vf-space-2); }

/* steps */
.steps {
  display: flex;
  align-items: center;
  gap: 0;
  margin: var(--vf-space-3) 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.steps::-webkit-scrollbar { display: none; }
.step {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}
.step-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1.5px solid var(--vf-border-strong);
  background: var(--vf-bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vf-text-3);
  transition: all 0.2s var(--vf-ease);
  flex: none;
}
.step-label {
  font-size: 11px;
  color: var(--vf-text-3);
  white-space: nowrap;
}
.step.done .step-dot {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  color: white;
}
.step.done .step-label { color: var(--vf-text-1); }
.step.current .step-dot {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  color: white;
  box-shadow: 0 0 0 4px var(--vf-primary-soft);
  animation: step-pulse 1.5s ease-in-out infinite;
}
.step.current .step-label { color: var(--vf-primary); font-weight: 600; }
@keyframes step-pulse {
  0%, 100% { box-shadow: 0 0 0 4px var(--vf-primary-soft); }
  50% { box-shadow: 0 0 0 7px transparent; }
}

.step-line {
  flex: 1;
  height: 1.5px;
  background: var(--vf-border);
  min-width: 12px;
  margin: 0 4px;
}
.step-line.done { background: var(--vf-primary); opacity: 0.6; }

/* track foot */
.track-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-3);
  margin-top: var(--vf-space-3);
  flex-wrap: wrap;
}
.track-tags { display: flex; gap: var(--vf-space-2); flex-wrap: wrap; }
.track-actions { display: flex; gap: var(--vf-space-2); }
.meta-pill {
  font-size: 11px;
  padding: 3px 8px;
  background: var(--vf-bg-3);
  border-radius: var(--vf-radius-full);
  color: var(--vf-text-2);
}
.meta-pill.warn { background: var(--vf-warn-soft); color: var(--vf-warn); }
.meta-pill.success { background: var(--vf-ok-soft); color: var(--vf-ok); }

/* buttons */
.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 5px 12px;
  border-radius: var(--vf-radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.ghost-btn:hover:not(:disabled) {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.ghost-btn.small { padding: 4px 10px; font-size: 11px; }
.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-primary);
  border: 1px solid var(--vf-primary);
  color: white;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.primary-btn:hover:not(:disabled) {
  background: var(--vf-primary-hover);
  border-color: var(--vf-primary-hover);
  transform: translateY(-1px);
}
.primary-btn.small { padding: 5px 10px; font-size: 11px; }
.primary-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.primary-btn.action-success { background: var(--vf-ok); border-color: var(--vf-ok); }
.primary-btn.action-success:hover:not(:disabled) { background: #16a34a; border-color: #16a34a; }
.primary-btn.action-default { background: var(--vf-bg-3); color: var(--vf-text-1); border-color: var(--vf-border); }
.primary-btn.action-default:hover:not(:disabled) { background: var(--vf-bg-hover); border-color: var(--vf-border-strong); }

/* detail */
.track-detail {
  margin-top: var(--vf-space-3);
  padding-top: var(--vf-space-3);
  border-top: 1px solid var(--vf-border);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.detail-block { display: flex; gap: var(--vf-space-3); font-size: 12px; }
.detail-label {
  flex: none;
  width: 56px;
  color: var(--vf-text-3);
}
.detail-tags { color: var(--vf-text-2); line-height: 1.6; }
.detail-lyrics {
  margin: 0;
  flex: 1;
  max-height: 220px;
  overflow-y: auto;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.8;
  color: var(--vf-text-2);
  white-space: pre-wrap;
}
.detail-platform { flex: 1; display: flex; flex-direction: column; gap: var(--vf-space-1); }
.detail-meta { margin: 0; font-size: 11px; color: var(--vf-text-3); }
.detail-config {
  margin-top: var(--vf-space-1);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.config-row { display: flex; gap: var(--vf-space-2); font-size: 11px; }
.config-k { flex: none; width: 96px; color: var(--vf-text-3); }
.config-v { color: var(--vf-text-2); }

/* modals */
.modal-lead { margin: 0 0 var(--vf-space-2); color: var(--vf-text-1); }
.modal-hint { margin: 0 0 var(--vf-space-4); font-size: 12px; color: var(--vf-text-3); }

.platform-picks { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.platform-pick {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  cursor: pointer;
  transition: background 0.15s;
}
.platform-pick:hover { background: var(--vf-bg-3); }
.pick-label { color: var(--vf-text-1); }
.pick-meta { margin-left: auto; font-size: 11px; color: var(--vf-text-3); }

.inbox-list { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.inbox-item {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.inbox-item:hover { background: var(--vf-bg-3); }
.inbox-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inbox-meta { display: flex; align-items: center; gap: var(--vf-space-2); font-size: 12px; color: var(--vf-text-3); }

@media (max-width: 760px) {
  .counters { grid-template-columns: repeat(5, 1fr); font-size: 10px; }
  .counter-n { font-size: 18px; }
}
</style>
