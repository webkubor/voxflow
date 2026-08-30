<script setup>
/**
 * 作品流水线看板 —— 「每首歌走到哪一步」以及「确认发版」这个决定。
 *
 * ## 为什么这块必须有
 *
 * 这个工具的价值是一条链：克隆声音 → 出歌 → 选定 → 发版 → 上架。
 * 但产物散在三处（Suno 云端、out/music/、publish/），状态只能靠翻目录猜。
 * 猜有两个东西是推不出来的：
 *
 * 1. **人的意图**。文件在 publish/ 下只说明打包过，不代表确认要发。
 * 2. **失败**。审核被拒、上传中断，文件系统里看不出来。
 *
 * ## 「确认发版」是这条链的闸门
 *
 * 发版之前不该做任何平台相关的事 —— 不知道发哪个平台，封面尺寸（汽水
 * 1440×1440 / 网易云 1400×1400）和文案风格都定不了。所以这一步不自动跳：
 * generated → selected 是「我要哪一首」（Suno 一次出两首），
 * selected → publishing 是「我确认发这首」。两个都是人点的。
 *
 * 阶段顺序直接用后端下发的 stages 数组，前端不抄一份 —— 抄了两边迟早对不上。
 */
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { usePipelineStore } from '../stores/pipeline';
import { useTasksStore } from '../stores/tasks';

const pipelineStore = usePipelineStore();
const tasksStore = useTasksStore();
const { stages, stageLabels, platforms, summary, tracks, error } = storeToRefs(pipelineStore);

const busyId = ref('');            // 正在提交的作品，避免连点
const showPublish = ref(false);    // 确认发版弹窗
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

/** 顶部计数条：只显示主流程五步，archived 不占位（那是支线不是进度）。 */
const counters = computed(() =>
  stages.value.map((s) => ({ key: s, label: stageLabels.value[s] || s, n: summary.value[s] || 0 })),
);

const stageIndex = (s) => stages.value.indexOf(s);

/**
 * 下一步该做什么。看板的重点不是展示状态，是告诉人「现在轮到你干嘛」——
 * 只显示状态的话，每次还要自己想一遍下一步是什么。
 */
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

  // 发版要先定平台 —— 各家封面尺寸和 AI 声明方式都不一样，
  // 不知道发哪儿就没法生成物料。
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
    // 先记平台、再推状态：反过来的话，中途失败会留下一个「发版中但不知道
    // 发去哪」的作品 —— 那种状态没人看得懂。
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

const platformLabel = (key) => platforms.value?.[key]?.label || key;

// 平台状态是后端存的自由字符串，界面上不能直接甩英文给人看。
// 没匹配上的原样显示 —— 总比显示「未知」丢掉信息强。
const PLATFORM_STATUS = {
  preparing: '备料中',
  uploaded: '已上传',
  reviewing: '审核中',
  online: '已上架',
  rejected: '被驳回',
};
const statusLabel = (s) => PLATFORM_STATUS[s] || s;
</script>

<template>
  <n-card title="作品流水线" size="small" class="board">
    <template #header-extra>
      <n-button size="tiny" secondary @click="load">刷新</n-button>
    </template>

    <!-- 计数条：一眼看清整体卡在哪一段 -->
    <div class="counters">
      <div v-for="c in counters" :key="c.key" class="counter" :class="{ 'is-zero': !c.n }">
        <span class="counter-n">{{ c.n }}</span>
        <span class="counter-label">{{ c.label }}</span>
      </div>
    </div>

    <n-alert v-if="error" type="error" :show-icon="false" class="board-err">{{ error }}</n-alert>

    <n-empty v-if="!tracks.length" description="还没有作品。去「AI 音乐」出一首，会自动登记到这里。" />

    <div v-else class="track-list">
      <div v-for="t in tracks" :key="t.id" class="track">
        <div class="track-head">
          <span class="track-title">{{ t.title }}</span>
          <n-tag size="small" round :type="t.stage === 'published' ? 'success' : 'info'">
            {{ t.stage_label }}
          </n-tag>
        </div>

        <!-- 进度点：走过的实心，当前的高亮，没到的空心 -->
        <div class="steps">
          <template v-for="(s, i) in stages" :key="s">
            <span
              class="step-dot"
              :class="{ done: i < stageIndex(t.stage), current: i === stageIndex(t.stage) }"
              :title="stageLabels[s]"
            ></span>
            <span v-if="i < stages.length - 1" class="step-line" :class="{ done: i < stageIndex(t.stage) }"></span>
          </template>
        </div>

        <div class="track-foot">
          <n-space size="small" align="center">
            <n-tag v-if="t.voice" size="small" :bordered="false">🎙️ {{ t.voice }}</n-tag>
            <n-tag
              v-for="(info, pk) in t.platforms"
              :key="pk"
              size="small"
              :bordered="false"
              type="warning"
            >
              {{ platformLabel(pk) }} · {{ statusLabel(info.status) }}
            </n-tag>
          </n-space>

          <n-button
            v-if="nextAction(t)"
            size="small"
            :type="nextAction(t).type"
            :loading="busyId === t.id"
            @click="advance(t)"
          >
            {{ nextAction(t).label }}
          </n-button>
        </div>
      </div>
    </div>

    <!-- 确认发版：这一下之后才谈平台物料 -->
    <n-modal
      v-model:show="showPublish"
      preset="card"
      title="确认发版"
      style="max-width: 440px"
    >
      <p class="modal-lead">
        <strong>{{ publishTrack?.title }}</strong> 要发到哪些平台？
      </p>
      <p class="modal-hint">
        各平台要求不同，选定后才能按对应 SOP 生成封面和文案。
      </p>

      <div class="platform-picks">
        <!-- platforms 是对象（key → 详情），不是数组 —— 必须用 (值, 键) 两个
             形参把 key 取出来，否则复选框的 value 是 undefined，
             勾了等于没勾，而且不报错。 -->
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
  </n-card>
</template>

<style scoped>
.board { margin-bottom: var(--vf-space-4); }

.counters {
  display: flex;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-4);
}
.counter {
  flex: 1;
  padding: var(--vf-space-3);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-3);
  text-align: center;
}
.counter.is-zero { opacity: .45; }
.counter-n {
  display: block;
  font-size: 20px;
  font-weight: 600;
  color: var(--vf-primary);
}
.counter-label {
  font-size: 12px;
  color: var(--vf-text-2);
}

.board-err { margin-bottom: var(--vf-space-3); }

.track-list { display: flex; flex-direction: column; gap: var(--vf-space-3); }
.track {
  padding: var(--vf-space-3) var(--vf-space-4);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg);
  background: var(--vf-bg-2);
}
.track-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-3);
}
.track-title { font-weight: 600; color: var(--vf-text-1); }

.steps {
  display: flex;
  align-items: center;
  margin: var(--vf-space-3) 0;
}
.step-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1.5px solid var(--vf-border-strong);
  flex: none;
}
.step-dot.done { background: var(--vf-primary); border-color: var(--vf-primary); opacity: .55; }
.step-dot.current {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  box-shadow: 0 0 0 4px var(--vf-primary-soft);
}
.step-line {
  flex: 1;
  height: 1.5px;
  background: var(--vf-border);
}
.step-line.done { background: var(--vf-primary); opacity: .45; }

.track-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-3);
}

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
}
.platform-pick:hover { background: var(--vf-bg-3); }
.pick-label { color: var(--vf-text-1); }
.pick-meta { margin-left: auto; font-size: 11px; color: var(--vf-text-3); }
</style>
