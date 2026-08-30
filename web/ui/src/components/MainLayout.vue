<template>
  <n-spin :show="globalLoading" :description="globalLoadingText" size="large" style="min-height: 100vh;">
    <n-layout style="height: 100vh; display: flex; flex-direction: column; position: relative; overflow: hidden; background-color: var(--vf-bg-0);">
      
      <!-- 顶部 Header：极简黑白高对比 -->
      <n-layout-header bordered class="app-header">
        <div class="header-left">
          <div class="brand-logo-container">
            <img :src="'/assets/branding/logo-icon.png'" class="logo-img" alt="Logo" />
            <span class="app-title">VoxFlow</span>
            <span class="app-version">v0.3.0</span>
          </div>

          <div class="header-platforms">
            <span class="platforms-label">全网发行支持:</span>
            <div class="platform-badges">
              <span class="plat-tag">汽水音乐</span>
              <span class="plat-tag">QQ音乐</span>
              <span class="plat-tag">网易云音乐</span>
            </div>
          </div>
        </div>

        <!-- 顶部右侧：资源与能力状态 -->
        <div class="header-right">
          <n-space size="small" align="center">
            <n-tooltip v-for="c in capBadges" :key="c.key" trigger="hover">
              <template #trigger>
                <div class="clean-status-badge" :class="c.ready ? 'status-ready' : 'status-pending'">
                  <span class="status-dot"></span>
                  <span class="status-name">{{ c.label }}</span>
                  <span v-if="c.num !== undefined" class="status-count">{{ c.num }}</span>
                </div>
              </template>
              {{ c.detail || (c.ready ? '服务正常' : '未就绪') }}
            </n-tooltip>
          </n-space>
        </div>
      </n-layout-header>

      <!-- 中部主内容布局 -->
      <n-layout has-sider style="flex: 1; overflow: hidden;">
        <!-- 左侧音色库工坊：纯净高对比 -->
        <n-layout-sider
          width="290"
          bordered
          content-style="display: flex; flex-direction: column; height: 100%;"
          class="clean-voice-sider"
        >
          <div class="sider-header">
            <div class="sider-title-wrap">
              <h3>音色库</h3>
              <span class="sider-count">{{ Object.keys(personas).length }}</span>
            </div>
            <button class="clean-add-btn" @click="showAddPersona = true">
              + 添加音色
            </button>
          </div>
          
          <div class="sider-content">
            <div 
              v-for="(p, key) in personas" 
              :key="key" 
              class="clean-persona-card"
              :class="{ 
                'is-selected': selectedPersona === key,
                'is-playing': previewKey === key
              }"
              @click="selectPersona(key)"
            >
              <!-- 试听进度底条 -->
              <div 
                v-if="previewKey === key" 
                class="audition-bar" 
                :style="{ width: previewProgress + '%' }"
              ></div>

              <div class="card-left-avatar">
                {{ (p.name || key).charAt(0) }}
              </div>

              <div class="card-center-info">
                <div class="card-top-row">
                  <span class="card-name">{{ p.name }}</span>
                  <span class="card-key">{{ key }}</span>
                </div>
                <p class="card-desc">{{ p.desc || p.instruction || '已装载声音特征' }}</p>
                <div class="card-badge-row">
                  <span class="card-status-dot" :class="p.has_audio ? 'dot-audio' : 'dot-no-audio'"></span>
                  <span class="card-status-text">{{ p.has_audio ? '样音已就绪' : '无样音' }}</span>
                </div>
              </div>

              <!-- 右侧操作 -->
              <div class="card-right-actions" @click.stop>
                <button 
                  v-if="p.has_audio" 
                  class="action-icon-btn play-btn" 
                  @click="togglePreview(key)"
                  :title="previewKey === key ? '暂停' : '试听'"
                >
                  <svg v-if="previewKey !== key" viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
                    <path d="M8 5V19L19 12L8 5Z"/>
                  </svg>
                  <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
                    <path d="M6 19H10V5H6V19ZM14 5V19H18V5H14Z"/>
                  </svg>
                </button>
                <button class="action-icon-btn" @click="openEditPersona(key)" title="编辑">✎</button>
                <button class="action-icon-btn del-btn" @click="confirmDeletePersona(key, p)" title="删除">✕</button>
              </div>
            </div>

            <div v-if="Object.keys(personas).length === 0" class="empty-state">
              <p>暂无音色资产</p>
              <span>点击右上角添加新音色</span>
            </div>
          </div>
        </n-layout-sider>

        <!-- 右侧主创作工作区 -->
        <n-layout-content content-style="padding: 20px 24px; display: flex; flex-direction: column; height: 100%;" class="clean-main-content">
          <n-tabs 
            v-model:value="currentTab" 
            type="line" 
            animated 
            style="height: 100%; display: flex; flex-direction: column;"
            @update:value="switchTab"
          >
            <n-tab-pane name="clone" tab="声音克隆">
              <CloneTab />
            </n-tab-pane>
            <n-tab-pane name="design" tab="音色设计">
              <DesignTab />
            </n-tab-pane>
            <n-tab-pane name="dialogue" tab="剧本创作">
              <DialogueTab />
            </n-tab-pane>
            <n-tab-pane name="suno" tab="AI 音乐">
              <SunoTab />
            </n-tab-pane>
            <n-tab-pane name="publish" tab="全网发行">
              <PublishTab />
            </n-tab-pane>
            <n-tab-pane name="library" tab="资产库">
              <LibraryTab />
            </n-tab-pane>
          </n-tabs>
        </n-layout-content>
      </n-layout>

      <!-- 底部高质感单色播放器 -->
      <GlobalPlayer />

      <!-- 右下角任务抽屉 -->
      <TaskPanel />

      <!-- 添加/编辑音色弹窗 -->
      <AddPersonaModal v-model:show="showAddPersona" />
      <EditPersonaModal
        v-model:show="showEditPersona"
        :persona-key="editingKey"
        :persona="personas[editingKey] || {}"
      />

      <!-- 隐藏的样音试听播放器 -->
      <audio 
        ref="previewPlayer" 
        style="display: none;" 
        @timeupdate="onPreviewProgress" 
        @ended="onPreviewEnded"
      ></audio>
    </n-layout>
  </n-spin>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import CloneTab from '../tabs/CloneTab.vue';
import DesignTab from '../tabs/DesignTab.vue';
import DialogueTab from '../tabs/DialogueTab.vue';
import SunoTab from '../tabs/SunoTab.vue';
import PublishTab from '../tabs/PublishTab.vue';
import LibraryTab from '../tabs/LibraryTab.vue';
import GlobalPlayer from './GlobalPlayer.vue';
import TaskPanel from './TaskPanel.vue';
import AddPersonaModal from './AddPersonaModal.vue';
import EditPersonaModal from './EditPersonaModal.vue';

import { useCapabilitiesStore } from '../stores/capabilities';
import { useLibraryStore } from '../stores/library';
import { usePipelineStore } from '../stores/pipeline';
import { useSunoStore } from '../stores/suno';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const capabilitiesStore = useCapabilitiesStore();
const libraryStore = useLibraryStore();
const pipelineStore = usePipelineStore();
const sunoStore = useSunoStore();
const synthStore = useSynthStore();
const tasksStore = useTasksStore();
const voicesStore = useVoicesStore();

const { capBadges } = storeToRefs(capabilitiesStore);
const { personas, selectedPersona } = storeToRefs(voicesStore);
const { globalLoading, globalLoadingText } = storeToRefs(synthStore);

const currentTab = ref('clone');
const showAddPersona = ref(false);
const showEditPersona = ref(false);
const editingKey = ref('');

const previewKey = ref('');
const previewProgress = ref(0);
const previewPlayer = ref(null);

const selectPersona = (key) => {
  voicesStore.selectPersona(key);
};

const togglePreview = (key) => {
  if (previewKey.value === key) {
    if (previewPlayer.value) {
      previewPlayer.value.pause();
      previewKey.value = '';
      previewProgress.value = 0;
    }
  } else {
    previewKey.value = key;
    previewProgress.value = 0;
    if (previewPlayer.value) {
      previewPlayer.value.src = `/api/preview-audio/${key}?t=${Date.now()}`;
      previewPlayer.value.play().catch(() => {
        tasksStore.showToast('无法播放样音', 'error');
        previewKey.value = '';
      });
    }
  }
};

const onPreviewProgress = (e) => {
  const audio = e.target;
  if (audio.duration) {
    previewProgress.value = (audio.currentTime / audio.duration) * 100;
  }
};

const onPreviewEnded = () => {
  previewKey.value = '';
  previewProgress.value = 0;
};

const openEditPersona = (key) => {
  editingKey.value = key;
  showEditPersona.value = true;
};

const confirmDeletePersona = (key, p) => {
  if (confirm(`确定要删除音色「${p.name || key}」的注册信息吗？`)) {
    voicesStore.deletePersona(key);
  }
};

const switchTab = (tab) => {
  currentTab.value = tab;
};

let pollTimer = null;
onMounted(async () => {
  // 用 allSettled 不用 all：Promise.all 里**任何一个 reject，后面的全不执行**。
  // 上一版第一个调的是 capabilitiesStore.fetchCapabilities()，
  // 而 store 里根本没这个方法 —— 第一步就 TypeError，音色库因此永远是空的，
  // 界面上只显示「暂无音色资产」，一个错都不报。最难查的那种。
  //
  // 每项独立起来，一个上游挂了只影响它自己；而且失败要说出来，不能吞。
  const jobs = [
    ['能力状态', () => capabilitiesStore.loadCaps()],
    ['音色库', () => voicesStore.loadPersonas()],
    ['任务队列', () => tasksStore.pollTasks()],
  ];
  const results = await Promise.allSettled(jobs.map(([, fn]) => fn()));
  results.forEach((r, i) => {
    if (r.status === 'rejected') {
      const name = jobs[i][0];
      console.error(`[VoxFlow] ${name}加载失败`, r.reason);
      tasksStore.showToast(`${name}加载失败：${r.reason?.message || r.reason}`, 'error');
    }
  });

  pollTimer = setInterval(() => {
    // 标签页在后台时不轮询 —— 开三个标签页等于三倍压力
    if (!document.hidden) tasksStore.pollTasks();
  }, 4000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
/* 顶部栏 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.brand-logo-container {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-img {
  width: 28px;
  height: 28px;
  border-radius: var(--vf-radius-xs);
  border: 1px solid var(--vf-border-strong);
}

.app-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--vf-text-1);
  letter-spacing: -0.02em;
}

.app-version {
  font-size: 11px;
  color: var(--vf-text-3);
  font-family: monospace;
}

.header-platforms {
  display: flex;
  align-items: center;
  gap: 10px;
  border-left: 1px solid var(--vf-border);
  padding-left: 16px;
}

.platforms-label {
  font-size: 12px;
  color: var(--vf-text-3);
}

.platform-badges {
  display: flex;
  gap: 6px;
}

.plat-tag {
  font-size: 11px;
  color: var(--vf-text-2);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  padding: 2px 8px;
  border-radius: var(--vf-radius-xs);
}

/* 状态 Badge */
.clean-status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--vf-radius-full);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  font-size: 12px;
  color: var(--vf-text-2);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-ready .status-dot { background: var(--vf-ok); }
.status-pending .status-dot { background: var(--vf-warn); }

.status-count {
  font-weight: 600;
  color: var(--vf-text-1);
  margin-left: 2px;
}

/* 左侧栏 */
.clean-voice-sider {
  user-select: none;
}

.sider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--vf-border);
}

.sider-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sider-title-wrap h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.sider-count {
  font-size: 11px;
  font-weight: 600;
  background: var(--vf-bg-active);
  color: var(--vf-text-2);
  padding: 1px 6px;
  border-radius: var(--vf-radius-xs);
}

.clean-add-btn {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border-strong);
  color: var(--vf-text-1);
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.clean-add-btn:hover {
  background: #ffffff;
  color: #000000;
  border-color: #ffffff;
}

.sider-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 音色卡片：干净利落的高对比面板 */
.clean-persona-card {
  position: relative;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.clean-persona-card:hover {
  background: var(--vf-bg-hover);
  border-color: var(--vf-border-strong);
}

.clean-persona-card.is-selected {
  background: var(--vf-bg-active);
  border-color: rgba(255, 255, 255, 0.4);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
}

.audition-bar {
  position: absolute;
  top: 0;
  left: 0;
  height: 2px;
  background: #ffffff;
  transition: width 0.1s linear;
}

.card-left-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--vf-radius-xs);
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  flex-shrink: 0;
}

.card-center-info {
  flex: 1;
  overflow: hidden;
}

.card-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}

.card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.card-key {
  font-size: 10px;
  color: var(--vf-text-3);
  font-family: monospace;
}

.card-desc {
  font-size: 11px;
  color: var(--vf-text-2);
  margin: 0 0 4px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-badge-row {
  display: flex;
  align-items: center;
  gap: 5px;
}

.card-status-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
}
.dot-audio { background: var(--vf-ok); }
.dot-no-audio { background: var(--vf-text-3); }

.card-status-text {
  font-size: 10px;
  color: var(--vf-text-3);
}

/* 操作图标 */
.card-right-actions {
  display: flex;
  align-items: center;
  gap: 3px;
  opacity: 0.7;
}

.clean-persona-card:hover .card-right-actions {
  opacity: 1;
}

.action-icon-btn {
  width: 22px;
  height: 22px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  font-size: 11px;
  border-radius: var(--vf-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-icon-btn:hover {
  background: #ffffff;
  color: #000000;
  border-color: #ffffff;
}

.action-icon-btn.del-btn:hover {
  background: var(--vf-err);
  color: #ffffff;
  border-color: var(--vf-err);
}

.empty-state {
  text-align: center;
  padding: 40px 10px;
  color: var(--vf-text-3);
}
.empty-state p { margin: 0 0 4px 0; font-size: 13px; color: var(--vf-text-2); }
.empty-state span { font-size: 11px; }
</style>
