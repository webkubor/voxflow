<template>
  <div 
    v-if="tasks.length > 0" 
    class="task-drawer-panel"
    :class="{ 'is-collapsed': taskPanelCollapsed }"
  >
    <!-- 面板头部，点击折叠/展开 -->
    <div class="panel-header" @click="taskPanelCollapsed = !taskPanelCollapsed">
      <div class="header-title">
        <span>📋 任务队列</span>
        <n-badge v-if="activeTaskCount > 0" :value="activeTaskCount" type="warning" />
      </div>
      <div class="header-icon">
        {{ taskPanelCollapsed ? '▲ 展开' : '▼ 折叠' }}
      </div>
    </div>

    <!-- 面板内容 -->
    <div v-show="!taskPanelCollapsed" class="panel-body">
      <div v-for="t in tasks" :key="t.id" class="task-item-card" :class="getTaskStatusClass(t)">
        <div class="task-info-row">
          <div class="task-type-badge" :class="t.type">
            {{ t.type === 'clone' ? '克隆' : '设计' }}
          </div>
          <span class="task-target-name">{{ getTaskTargetName(t) }}</span>
          
          <!-- 取消排队任务 -->
          <n-button 
            v-if="t.status === 'queued'" 
            circle 
            size="tiny" 
            type="error" 
            quaternary
            @click.stop="cancelTask(t.id)"
          >
            ✕
          </n-button>
        </div>

        <!-- 任务状态与报错 -->
        <div class="task-status-row">
          <span class="status-text">{{ getTaskStatusLabel(t) }}</span>
          <span class="time-text">{{ formatTime(t.created_at) }}</span>
        </div>

        <div v-if="t.status === 'error'" class="task-error-msg">
          {{ t.error || '合成异常，请检查终端日志' }}
        </div>

        <!-- 任务完成后快捷操作 -->
        <div v-if="t.status === 'done'" class="task-done-actions">
          <n-button 
            v-if="t.result && t.result.urls && t.result.urls.length > 0"
            size="tiny" 
            type="primary" 
            secondary 
            @click="playAudio(t.result.urls[0], t.result.files[0])"
          >
            ▶ 试听
          </n-button>
          <n-button 
            v-if="t.result && t.result.urls && t.result.urls.length > 0"
            size="tiny" 
            type="default" 
            secondary 
            tag="a"
            :href="t.result.urls[0]"
            :download="t.result.files[0]"
          >
            ⬇ 下载
          </n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 右下角任务队列折叠抽屉
 * 职责：展示后台声音合成任务的队列进度、报错信息及完成后试听/下载
 * API 来源：与 /api/tasks 状态同步，支持 DELETE /api/tasks/{id} 取消排队
 */
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useLibraryStore } from '../stores/library';
import { useTasksStore } from '../stores/tasks';

const tasksStore = useTasksStore();
const { tasks, taskPanelCollapsed } = storeToRefs(tasksStore);
const { cancelTask } = tasksStore;
const { playAudio } = useLibraryStore();

// 活跃进行中的任务数量
const activeTaskCount = computed(() => {
  return tasks.value.filter(x => x.status === 'queued' || x.status === 'running').length;
});

// 解析任务目标对象
const getTaskTargetName = (t) => {
  if (t.type === 'clone') {
    return t.params?.persona || '未知音色';
  }
  return t.params?.voice_name || '音色设计';
};

// 状态样式
const getTaskStatusClass = (t) => {
  return {
    'status-queued': t.status === 'queued',
    'status-running': t.status === 'running',
    'status-done': t.status === 'done',
    'status-error': t.status === 'error',
  };
};

// 中文化状态
const getTaskStatusLabel = (t) => {
  if (t.status === 'queued') return '排队中...';
  if (t.status === 'running') {
    return t.stage ? `进行中 (${t.stage})` : '处理中...';
  }
  if (t.status === 'done') return '✅ 完成';
  if (t.status === 'error') return '❌ 失败';
  if (t.status === 'cancelled') return '已取消';
  return t.status;
};

// 格式化时间
const formatTime = (timeStr) => {
  if (!timeStr) return '';
  try {
    const d = new Date(timeStr);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  } catch (e) {
    return '';
  }
};
</script>

<style scoped>
.task-drawer-panel {
  position: fixed;
  bottom: 85px; /* 避开播放器 */
  right: 20px;
  width: 300px;
  max-height: 400px;
  background-color: #1c1c20;
  border: 1px solid var(--vf-bg-4);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  z-index: 999;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: max-height 0.2s ease, width 0.2s ease;
}

.task-drawer-panel.is-collapsed {
  max-height: 40px;
}

.panel-header {
  height: 40px;
  background-color: #26262b;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--vf-bg-4);
  user-select: none;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.header-icon {
  font-size: 12px;
  color: var(--vf-text-2);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 任务卡片项 */
.task-item-card {
  padding: 10px;
  border-radius: 6px;
  background-color: #151518;
  border-left: 4px solid var(--vf-text-3);
}

.task-item-card.status-queued {
  border-left-color: var(--vf-text-3);
}

.task-item-card.status-running {
  border-left-color: var(--vf-gold);
  animation: borderPulse 1.5s infinite;
}

.task-item-card.status-done {
  border-left-color: var(--vf-ok);
}

.task-item-card.status-error {
  border-left-color: var(--vf-err);
}

@keyframes borderPulse {
  0% { border-left-color: var(--vf-gold); }
  50% { border-left-color: rgba(240, 160, 32, 0.4); }
  100% { border-left-color: var(--vf-gold); }
}

.task-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.task-type-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: bold;
}

.task-type-badge.clone {
  background-color: rgba(24, 160, 88, 0.15);
  color: var(--vf-ok);
}

.task-type-badge.design {
  background-color: rgba(32, 128, 240, 0.15);
  color: var(--vf-info);
}

.task-target-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-1);
  flex: 1;
  margin-left: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-status-row {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--vf-text-2);
}

.task-error-msg {
  font-size: 11px;
  color: var(--vf-err);
  background-color: rgba(208, 48, 80, 0.08);
  padding: 4px 6px;
  border-radius: 4px;
  margin-top: 6px;
  word-break: break-all;
}

.task-done-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
