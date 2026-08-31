<template>
  <aside class="task-panel" role="complementary" aria-label="任务队列">
    <header class="task-head">
      <div class="task-head-left">
        <Icon name="layers" size="sm" />
        <span>任务队列</span>
        <span v-if="activeCount > 0" class="task-head-badge">{{ activeCount }}</span>
      </div>
      <div class="task-head-right">
        <button class="head-btn" title="全部收起" @click="tasksStore.taskPanelCollapsed = true">
          <Icon name="collapse" size="sm" />
        </button>
        <button class="head-btn" title="关闭面板" @click="$emit('close')">
          <Icon name="close" size="sm" />
        </button>
      </div>
    </header>

    <div v-show="!tasksStore.taskPanelCollapsed" class="task-body scroll-y">
      <div v-for="t in tasks" :key="t.id" class="task-card" :class="`status-${t.status}`">
        <div class="task-card-head">
          <TaskTypeBadge :type="t.type" />
          <span class="task-name" :title="getTaskTargetName(t)">{{ getTaskTargetName(t) }}</span>
          <button
            v-if="t.status === 'queued'"
            class="head-btn danger"
            title="取消任务"
            @click="cancelTask(t.id)"
          >
            <Icon name="close" size="sm" />
          </button>
        </div>

        <div v-if="t.status === 'running' && t.stage" class="task-progress">
          <div class="task-progress-bar">
            <div class="task-progress-fill" :style="{ width: stagePercent(t.stage) + '%' }"></div>
          </div>
          <span class="task-progress-label">{{ t.stage }}</span>
        </div>

        <div class="task-meta">
          <span class="task-status">{{ statusLabel(t.status) }}</span>
          <span class="task-time">{{ formatTime(t.created_at) }}</span>
        </div>

        <p v-if="t.status === 'error' && t.error" class="task-error">{{ t.error }}</p>

        <div v-if="t.status === 'done' && t.result?.urls?.length" class="task-actions">
          <button class="action-btn primary" @click="playAudio(t.result.urls[0], t.result.files[0])">
            <Icon name="play" size="sm" />
            <span>试听</span>
          </button>
          <a
            class="action-btn"
            :href="t.result.urls[0]"
            :download="t.result.files[0]"
          >
            <Icon name="download" size="sm" />
            <span>下载</span>
          </a>
        </div>
      </div>

      <div v-if="tasks.length === 0" class="task-empty">
        <Icon name="check" size="md" />
        <span>暂无任务</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
/**
 * 任务队列面板 —— 由 MainLayout 顶栏铃铛控制开合，位置从右下半抽屉挪到
 * 右侧侧栏，能完整看见每条任务的进度和报错。关闭按钮是用户主动的"不想看了"出口，
 * 不是折叠。
 *
 * ## 进度条
 *
 * 后端的 stage 字段是阶段名字符串（"loading_model" / "synthesizing" / "finalizing"），
 * 这里按前缀分组映射成 0~100 的进度估算 —— 真实进度以后端 stage_count 为准。
 */
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useLibraryStore } from '../stores/library';
import { useTasksStore } from '../stores/tasks';
import Icon from './Icon.vue';
import TaskTypeBadge from './TaskTypeBadge.vue';

defineEmits(['close']);

const tasksStore = useTasksStore();
const { tasks } = storeToRefs(tasksStore);
const { cancelTask } = tasksStore;
const { playAudio } = useLibraryStore();

const activeCount = computed(
  () => tasks.value.filter((x) => x.status === 'queued' || x.status === 'running').length,
);

const getTaskTargetName = (t) => {
  if (t.type === 'clone') return t.params?.persona || '未指定音色';
  if (t.type === 'design') return t.params?.voice_name || '音色设计';
  if (t.type === 'suno') return t.params?.title || 'Suno 任务';
  if (t.type === 'dialogue') return t.params?.title || '剧本任务';
  return t.type;
};

const STATUS_LABEL = {
  queued: '排队中',
  running: '处理中',
  done: '已完成',
  error: '失败',
  cancelled: '已取消',
};
const statusLabel = (s) => STATUS_LABEL[s] || s;

const STAGE_PROGRESS = {
  loading_model: 25,
  preprocessing: 40,
  cloning: 55,
  synthesizing: 75,
  finalizing: 90,
  encoding: 95,
};
const stagePercent = (stage) => STAGE_PROGRESS[stage] ?? 50;

const formatTime = (timeStr) => {
  if (!timeStr) return '';
  try {
    const d = new Date(timeStr);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  } catch { return ''; }
};
</script>

<style scoped>
.task-panel {
  position: fixed;
  top: calc(var(--vf-header-h) + var(--vf-space-3));
  right: var(--vf-space-3);
  width: 320px;
  max-height: calc(100vh - var(--vf-header-h) - var(--vf-player-h) - var(--vf-space-7));
  background: var(--vf-bg-1);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  box-shadow: var(--vf-shadow-elevated);
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slide-in 0.2s var(--vf-ease);
}
@keyframes slide-in {
  from { transform: translateX(20px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

.task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--vf-space-3) var(--vf-space-4);
  background: var(--vf-bg-2);
  border-bottom: 1px solid var(--vf-border);
}
.task-head-left {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.task-head-badge {
  background: var(--vf-warn-soft);
  color: var(--vf-warn);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
  font-size: 10px;
  font-weight: 600;
}
.task-head-right { display: flex; gap: var(--vf-space-1); }
.head-btn {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  width: 26px;
  height: 26px;
  border-radius: var(--vf-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.head-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
}
.head-btn.danger:hover { color: var(--vf-err); }

.task-body {
  padding: var(--vf-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-2);
}

.task-card {
  padding: var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  border-left: 3px solid var(--vf-text-3);
}
.task-card.status-running {
  border-left-color: var(--vf-warn);
  background: linear-gradient(90deg, var(--vf-warn-soft) 0%, var(--vf-bg-2) 50%);
  animation: pulse-border 1.5s ease-in-out infinite;
}
.task-card.status-done { border-left-color: var(--vf-ok); }
.task-card.status-error { border-left-color: var(--vf-err); }
.task-card.status-queued { border-left-color: var(--vf-text-3); }
.task-card.status-cancelled { border-left-color: var(--vf-text-3); opacity: 0.6; }

@keyframes pulse-border {
  0%, 100% { border-left-color: var(--vf-warn); }
  50% { border-left-color: rgba(234, 179, 8, 0.4); }
}

.task-card-head {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-2);
}
.task-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-1);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-progress {
  margin-bottom: var(--vf-space-2);
}
.task-progress-bar {
  width: 100%;
  height: 3px;
  background: var(--vf-bg-3);
  border-radius: var(--vf-radius-full);
  overflow: hidden;
  margin-bottom: 4px;
}
.task-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--vf-warn), var(--vf-primary));
  border-radius: var(--vf-radius-full);
  transition: width 0.3s var(--vf-ease);
}
.task-progress-label {
  font-size: 10px;
  color: var(--vf-text-3);
  font-family: ui-monospace, monospace;
}

.task-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--vf-text-2);
}
.task-status { font-weight: 500; }
.task-time { color: var(--vf-text-3); font-variant-numeric: tabular-nums; }

.task-error {
  margin: var(--vf-space-2) 0 0;
  font-size: 11px;
  color: var(--vf-err);
  background: var(--vf-err-soft);
  padding: var(--vf-space-2);
  border-radius: var(--vf-radius-xs);
  word-break: break-all;
}

.task-actions {
  display: flex;
  gap: var(--vf-space-2);
  margin-top: var(--vf-space-2);
}
.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-1);
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.15s;
}
.action-btn:hover {
  background: var(--vf-bg-hover);
  border-color: var(--vf-border-strong);
}
.action-btn.primary {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  color: white;
}
.action-btn.primary:hover {
  background: var(--vf-primary-hover);
  border-color: var(--vf-primary-hover);
}

.task-empty {
  text-align: center;
  padding: var(--vf-space-7) var(--vf-space-3);
  color: var(--vf-text-3);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
}
</style>
