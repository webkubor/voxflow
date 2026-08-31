<template>
  <n-spin :show="globalLoading" :description="globalLoadingText" size="large" style="min-height: 100vh;">
    <n-layout class="app-shell">
      <!-- 顶部 Header：极简 Logo + 能力状态 -->
      <n-layout-header bordered class="app-header">
        <div class="header-left">
          <button
            class="sider-toggle"
            :title="siderCollapsed ? '展开音色库' : '折叠音色库'"
            @click="siderCollapsed = !siderCollapsed"
          >
            <Icon name="menu" size="sm" />
          </button>
          <div class="brand">
            <img :src="'/assets/branding/logo-icon.png'" class="brand-logo" alt="VoxFlow" />
            <div class="brand-text">
              <span class="brand-name">VoxFlow</span>
              <span class="brand-sub">声流</span>
            </div>
          </div>
        </div>

        <div class="header-right">
          <!-- 能力状态：用 popover 而非 tag 内混排文字 -->
          <div class="caps">
            <n-tooltip v-for="c in capBadges" :key="c.key" trigger="hover" placement="bottom-end">
              <template #trigger>
                <div class="cap-chip" :class="c.ready ? 'ok' : 'off'">
                  <span class="cap-dot"></span>
                  <span class="cap-label">{{ c.label }}</span>
                  <span class="cap-what">{{ c.what }}</span>
                </div>
              </template>
              <div class="cap-popover">
                <div class="cap-pop-row">
                  <span class="cap-pop-k">状态</span>
                  <span class="cap-pop-v" :class="c.ready ? 'ok' : 'off'">
                    {{ c.ready ? '● 已就绪' : '○ 未就绪' }}
                  </span>
                </div>
                <div class="cap-pop-row">
                  <span class="cap-pop-k">使用</span>
                  <span class="cap-pop-v">{{ c.what }}</span>
                </div>
                <div v-if="c.detail" class="cap-pop-row">
                  <span class="cap-pop-k">说明</span>
                  <span class="cap-pop-v">{{ c.detail }}</span>
                </div>
              </div>
            </n-tooltip>
          </div>

          <!-- 任务队列角标 -->
          <button
            class="bell"
            :class="{ 'has-active': activeTaskCount > 0 }"
            :title="`任务队列（${activeTaskCount} 进行中）`"
            @click="toggleTaskPanel"
          >
            <Icon name="bell" size="md" />
            <span v-if="activeTaskCount > 0" class="bell-num">{{ activeTaskCount }}</span>
          </button>
        </div>
      </n-layout-header>

      <!-- 中部主内容 -->
      <n-layout has-sider class="app-body">
        <!-- 左侧音色库 -->
        <PersonaSidebar
          :collapsed="siderCollapsed"
          @toggle-collapse="siderCollapsed = !siderCollapsed"
          @add-persona="showAddPersona = true"
          @edit-persona="openEditPersona"
          @delete-persona="confirmDeletePersona"
        />

        <!-- 右侧主创作工作区 -->
        <n-layout-content class="main-content">
          <!-- Tab 导航：图标 + 文字 -->
          <nav class="tab-nav" role="tablist">
            <button
              v-for="t in tabs"
              :key="t.name"
              class="tab-nav-item"
              :class="{ active: currentTab === t.name }"
              role="tab"
              :aria-selected="currentTab === t.name"
              @click="goTab(t.name)"
            >
              <Icon :name="t.icon" size="md" />
              <span class="tab-nav-label">{{ t.label }}</span>
            </button>
          </nav>

          <!-- 共享的「当前音色」状态条 -->
          <div v-if="needsPersona" class="current-persona-row">
            <CurrentPersonaChip />
            <div v-if="currentTab === 'clone' || currentTab === 'design'" class="model-pill">
              <span class="model-pill-label">模型</span>
              <span class="model-pill-value">{{ modelLabel }}</span>
              <n-progress
                v-if="modelDownloading"
                type="line"
                :percentage="modelProgress"
                :show-indicator="false"
                :height="3"
                class="model-pill-bar"
              />
            </div>
          </div>

          <!-- Tab 主体：保留 n-tabs 提供的路由同步能力 -->
          <n-tabs
            v-model:value="currentTab"
            type="line"
            animated
            class="hidden-tabs"
          >
            <n-tab-pane name="clone" tab="克隆"><CloneTab /></n-tab-pane>
            <n-tab-pane name="design" tab="设计"><DesignTab /></n-tab-pane>
            <n-tab-pane name="dialogue" tab="剧本"><DialogueTab /></n-tab-pane>
            <n-tab-pane name="suno" tab="音乐"><SunoTab /></n-tab-pane>
            <n-tab-pane name="works" tab="看板"><PipelineBoard /></n-tab-pane>
            <n-tab-pane name="publish" tab="发行"><PublishTab /></n-tab-pane>
            <n-tab-pane name="library" tab="资产"><LibraryTab /></n-tab-pane>
          </n-tabs>
        </n-layout-content>
      </n-layout>

      <!-- 底部播放器 -->
      <GlobalPlayer />

      <!-- 任务抽屉 -->
      <TaskPanel v-if="taskPanelOpen" @close="taskPanelOpen = false" />

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
/**
 * 应用主布局。
 *
 * ## 结构
 *
 *   Header  |  Logo | 能力 chips | 任务铃铛
 *   Sider   |  音色库（可折叠成 64px 窄条）
 *   Content |  Tab 导航（图标 + 文字）
 *           |  当前音色条
 *           |  Tab 主体
 *   Player  |  固定底部，72px 高
 *
 * ## Tab 导航为啥手搓
 *
 * 之前用 n-tabs 自带胶囊 tab，但它只能放文字。7 个 tab 没图标挤一起
 * 难分辨。换成自定义按钮 + 路由切换，n-tabs 留在下面当「路由 ↔ tab」的
 * 同步源（它绑了 v-model 到 currentTab）。视觉上不显示，但行为仍在。
 */
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { BOARD_POLL_MS } from '../config/constants';
import { TAB_NAMES } from '../router';
import { storeToRefs } from 'pinia';
// 异步组件：路由切到哪一屏才加载哪一屏，首屏不打包这 6 个 chunk
const CloneTab = defineAsyncComponent(() => import('../tabs/CloneTab.vue'));
const DesignTab = defineAsyncComponent(() => import('../tabs/DesignTab.vue'));
const DialogueTab = defineAsyncComponent(() => import('../tabs/DialogueTab.vue'));
const SunoTab = defineAsyncComponent(() => import('../tabs/SunoTab.vue'));
const PipelineBoard = defineAsyncComponent(() => import('./PipelineBoard.vue'));
const PublishTab = defineAsyncComponent(() => import('../tabs/PublishTab.vue'));
const LibraryTab = defineAsyncComponent(() => import('../tabs/LibraryTab.vue'));
import GlobalPlayer from './GlobalPlayer.vue';
import TaskPanel from './TaskPanel.vue';
import AddPersonaModal from './AddPersonaModal.vue';
import EditPersonaModal from './EditPersonaModal.vue';
import PersonaSidebar from './PersonaSidebar.vue';
import CurrentPersonaChip from './CurrentPersonaChip.vue';
import Icon from './Icon.vue';

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
const { globalLoading, globalLoadingText, tasks, taskPanelCollapsed } = storeToRefs(tasksStore);
const { modelStatus } = storeToRefs(capabilitiesStore);
const { player } = storeToRefs(libraryStore);

// 「模型未就绪」时哪些 tab 需要显示下载提示
const NEEDS_PERSONA_TABS = new Set(['clone', 'design', 'dialogue']);
const route = useRoute();
const router = useRouter();

const currentTab = computed({
  get: () => (TAB_NAMES.has(route.name) ? route.name : 'clone'),
  set: (tab) => {
    if (route.name !== tab) router.push({ name: tab });
  },
});

const tabs = [
  { name: 'clone', label: '声音克隆', icon: 'clone' },
  { name: 'design', label: '音色设计', icon: 'design' },
  { name: 'dialogue', label: '剧本创作', icon: 'dialogue' },
  { name: 'suno', label: 'AI 音乐', icon: 'suno' },
  { name: 'works', label: '作品看板', icon: 'board' },
  { name: 'publish', label: '全网发行', icon: 'publish' },
  { name: 'library', label: '资产库', icon: 'library' },
];

const goTab = (name) => {
  if (route.name !== name) router.push({ name });
};

// 哪些 tab 需要显示「当前音色」条
const needsPersona = computed(() => NEEDS_PERSONA_TABS.has(currentTab.value));

// 模型下载进度 / 状态文本
const modelDownloading = computed(() => {
  if (currentTab.value === 'design') return !!modelStatus.value.design.downloading;
  return !!modelStatus.value.base.downloading;
});
const modelProgress = computed(() => {
  if (currentTab.value === 'design') return Math.round(modelStatus.value.design.progress || 0);
  return Math.round(modelStatus.value.base.progress || 0);
});
const modelLabel = computed(() => {
  if (currentTab.value === 'design') {
    return modelStatus.value.design.ready ? 'VoiceDesign · 就绪' : 'VoiceDesign · 未就绪';
  }
  return modelStatus.value.base.ready ? 'Qwen3-TTS · 就绪' : 'Qwen3-TTS · 未就绪';
});

// 侧栏折叠
const siderCollapsed = ref(false);

// 任务面板：从「右下半抽屉」挪到由 header 铃铛开关控制
const taskPanelOpen = ref(false);
const toggleTaskPanel = () => {
  taskPanelOpen.value = !taskPanelOpen.value;
  if (taskPanelOpen.value) taskPanelCollapsed.value = false;
};

// 进行中任务数
const activeTaskCount = computed(
  () => tasks.value.filter((t) => t.status === 'queued' || t.status === 'running').length,
);

// 弹窗控制
const showAddPersona = ref(false);
const showEditPersona = ref(false);
const editingKey = ref('');

// 试听
const previewPlayer = ref(null);
const previewKey = computed(() => voicesStore.previewKey);
const previewProgress = computed(() => voicesStore.previewProgress);
const onPreviewProgress = (e) => voicesStore.onPreviewProgress(e);
const onPreviewEnded = () => voicesStore.onPreviewEnded();

const togglePreview = (key) => voicesStore.togglePreview(key);

const openEditPersona = (key) => {
  editingKey.value = key;
  showEditPersona.value = true;
};

const confirmDeletePersona = (key) => {
  const p = personas.value[key];
  if (confirm(`确定要删除音色「${p?.name || key}」的注册信息吗？`)) {
    voicesStore.deletePersona(key);
  }
};

let pollTimer = null;
onMounted(async () => {
  // 用 allSettled 不用 all：Promise.all 里**任何一个 reject，后面的全不执行**。
  // 每项独立起来，一个上游挂了只影响它自己；而且失败要说出来，不能吞。
  const jobs = [
    ['能力状态', () => capabilitiesStore.loadCaps()],
    ['模型状态', () => capabilitiesStore.checkStatus()],
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
    if (!document.hidden) tasksStore.pollTasks();
  }, BOARD_POLL_MS);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});

// 给 SunoTab 这种需要刷新状态的子组件用的 expose 触发器
defineExpose({});
</script>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  background-color: var(--vf-bg-0);
}

/* ── Header ── */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 var(--vf-space-5);
  gap: var(--vf-space-4);
  flex: none;
}
.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
}

.sider-toggle {
  background: transparent;
  border: 1px solid transparent;
  color: var(--vf-text-3);
  width: 32px;
  height: 32px;
  border-radius: var(--vf-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.sider-toggle:hover {
  color: var(--vf-text-1);
  background: var(--vf-bg-hover);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}
.brand-logo {
  width: 28px;
  height: 28px;
  border-radius: var(--vf-radius-xs);
}
.brand-text {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--vf-text-1);
  letter-spacing: -0.02em;
}
.brand-sub {
  font-size: 11px;
  color: var(--vf-text-3);
}

/* 能力状态 */
.caps {
  display: flex;
  gap: var(--vf-space-2);
}
.cap-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-full);
  font-size: 12px;
  cursor: help;
  transition: border-color 0.15s;
}
.cap-chip:hover { border-color: var(--vf-border-strong); }
.cap-chip.ok .cap-dot { background: var(--vf-ok); }
.cap-chip.off .cap-dot { background: var(--vf-text-3); }
.cap-dot {
  width: 6px; height: 6px; border-radius: 50%;
  box-shadow: 0 0 0 2px currentColor;
  background: currentColor;
}
.cap-chip.ok { color: var(--vf-ok); }
.cap-chip.off { color: var(--vf-text-3); }
.cap-label {
  color: var(--vf-text-1);
  font-weight: 500;
}
.cap-what {
  color: var(--vf-text-2);
  font-size: 11px;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cap-popover { font-size: 12px; min-width: 200px; }
.cap-pop-row {
  display: flex; gap: var(--vf-space-3); padding: 3px 0;
}
.cap-pop-k { color: var(--vf-text-3); flex: none; width: 36px; }
.cap-pop-v { color: var(--vf-text-1); }
.cap-pop-v.ok { color: var(--vf-ok); }
.cap-pop-v.off { color: var(--vf-warn); }

/* 任务铃铛 */
.bell {
  position: relative;
  background: transparent;
  border: 1px solid var(--vf-border);
  width: 36px;
  height: 36px;
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-2);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.bell:hover { color: var(--vf-text-1); background: var(--vf-bg-hover); }
.bell.has-active {
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
}
.bell-num {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: var(--vf-err);
  color: white;
  border-radius: var(--vf-radius-full);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 0 2px var(--vf-bg-0);
}

/* ── 主体 ── */
.app-body {
  flex: 1;
  overflow: hidden;
}

.main-content {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: var(--vf-space-5) var(--vf-space-6) 0;
  /* 给底部播放器留位置 —— 这是上一版漏掉的，全局播放器会盖住最后一排 */
  padding-bottom: calc(var(--vf-player-h) + var(--vf-space-4));
}

/* Tab 导航 */
.tab-nav {
  display: flex;
  gap: var(--vf-space-1);
  padding: var(--vf-space-2);
  background: var(--vf-bg-1);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg);
  margin-bottom: var(--vf-space-4);
  overflow-x: auto;
  scrollbar-width: none;
}
.tab-nav::-webkit-scrollbar { display: none; }

.tab-nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--vf-radius-md);
  color: var(--vf-text-2);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
  white-space: nowrap;
  flex: none;
}
.tab-nav-item:hover {
  color: var(--vf-text-1);
  background: var(--vf-bg-hover);
}
.tab-nav-item.active {
  color: var(--vf-text-1);
  background: var(--vf-bg-active);
  border-color: var(--vf-border-strong);
  font-weight: 600;
}
.tab-nav-label { font-size: 13px; }

/* 当前音色条 */
.current-persona-row {
  display: flex;
  align-items: stretch;
  gap: var(--vf-space-3);
  margin-bottom: var(--vf-space-4);
}
.current-persona-row > :first-child { flex: 1; }

.model-pill {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  padding: 0 var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  font-size: 12px;
  position: relative;
  overflow: hidden;
}
.model-pill-label { color: var(--vf-text-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.model-pill-value { color: var(--vf-text-1); font-weight: 600; }
.model-pill-bar {
  position: absolute;
  left: 0; right: 0; bottom: 0;
}

/* 隐藏 n-tabs —— 只用它做路由同步，导航我们自己渲染 */
.hidden-tabs {
  display: none;
}
</style>
