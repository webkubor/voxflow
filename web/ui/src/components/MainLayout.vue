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
                <!-- Suno 专项：套餐 / credits / 重置日 -->
                <template v-if="c.key === 'suno'">
                  <div v-if="c.plan" class="cap-pop-row">
                    <span class="cap-pop-k">套餐</span>
                    <span class="cap-pop-v">{{ c.plan }}</span>
                  </div>
                  <div v-if="c.creditsRemaining !== undefined" class="cap-pop-row">
                    <span class="cap-pop-k">剩余</span>
                    <span class="cap-pop-v">
                      {{ c.creditsRemaining }} credits
                      <span v-if="c.creditsTotal" class="cap-pop-sub">/ {{ c.creditsTotal }}</span>
                    </span>
                  </div>
                  <div v-if="c.creditsTotal !== undefined && c.creditsRemaining !== undefined" class="cap-pop-row">
                    <span class="cap-pop-k">已用</span>
                    <span class="cap-pop-v">{{ c.creditsTotal - c.creditsRemaining }} credits</span>
                  </div>
                  <div v-if="c.renewDate" class="cap-pop-row">
                    <span class="cap-pop-k">续费</span>
                    <span class="cap-pop-v">{{ formatRenewDate(c.renewDate) }}</span>
                  </div>
                </template>
                <div v-if="c.detail" class="cap-pop-row">
                  <span class="cap-pop-k">说明</span>
                  <span class="cap-pop-v">{{ c.detail }}</span>
                </div>
              </div>
            </n-tooltip>
          </div>

          <!-- 错误日志角标 -->
          <button
            class="bell"
            :class="{ 'has-active': errorCount > 0, 'has-error': errorCount > 0 }"
            :title="`错误日志（${errorCount} 条）`"
            @click="toggleErrorPanel"
          >
            <Icon name="warning" size="md" />
            <span v-if="errorCount > 0" class="bell-num error">{{ errorCount }}</span>
          </button>

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
          ref="sidebarRef"
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
            <n-tab-pane name="ops" tab="运营"><OpsTab /></n-tab-pane>
          </n-tabs>
        </n-layout-content>
      </n-layout>

      <!-- 底部播放器 -->
      <GlobalPlayer ref="playerRef" />

      <!-- 任务抽屉 -->
      <TaskPanel v-if="taskPanelOpen" @close="taskPanelOpen = false" />

      <!-- 错误日志面板 -->
      <ErrorLogPanel v-if="errorPanelOpen" @close="errorPanelOpen = false" />

      <!-- 快捷键帮助 -->
      <ShortcutHelp v-model:show="helpOpen" />

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
import { computed, defineAsyncComponent, h, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { BOARD_POLL_MS } from '../config/constants';
import { TAB_NAMES } from '../router';
import { storeToRefs } from 'pinia';
/**
 * 异步组件：路由切到哪一屏才加载哪一屏，首屏不打包这几个 chunk。
 *
 * ⚠️ **加载失败必须说出来**。`defineAsyncComponent` 默认在失败时什么都不渲染
 * 也不报错 —— 那一屏就是纯空白，人会以为「数据没了」。而最常见的失败原因
 * 恰恰不是数据问题：前端重新构建后 chunk 文件名变了，已经开着的老页面
 * 手里那个名字在服务器上已经不存在（`vite build` 会清空 assets 目录）。
 *
 * `lazyTab` 给每个都挂上错误兜底：失败时显示一句人话 + 一个刷新按钮，
 * 而不是让人对着空白屏猜。真正的自动救援在 main.js 的 vite:preloadError，
 * 这里是它没兜住时的最后一道。
 *
 * ⚠️ 兜底组件必须用 `render()` + `h()`，**不能用 `template:` 字符串** ——
 * 生产构建的 Vue 不含运行时模板编译器，字符串模板在 dev 下好好的，
 * 打包后静默不渲染。而这个组件恰恰只在生产、只在出问题时才出现，
 * 是最不容易被发现写错的地方（第一版就栽在这儿）。
 */
const lazyTab = (loader, label) => defineAsyncComponent({
  loader,
  delay: 120,          // 120ms 内加载完就不闪 loading，避免本地秒开时的闪烁
  timeout: 20000,
  errorComponent: {
    name: 'TabLoadError',
    render: () => h('div', { class: 'tab-load-error' }, [
      h('p', { class: 'tle-title' }, `「${label}」这一屏没加载出来`),
      h('p', { class: 'tle-hint' }, [
        '多半是前端更新过、而这个页面还是旧的 —— 刷新一下就好。',
        h('b', ' 你的数据没有丢。'),
      ]),
      h('button', {
        class: 'tle-btn',
        onClick: () => window.location.reload(),
      }, '刷新页面'),
    ]),
  },
});

const CloneTab = lazyTab(() => import('../tabs/CloneTab.vue'), '声音克隆');
const DesignTab = lazyTab(() => import('../tabs/DesignTab.vue'), '音色设计');
const DialogueTab = lazyTab(() => import('../tabs/DialogueTab.vue'), '剧本创作');
const SunoTab = lazyTab(() => import('../tabs/SunoTab.vue'), 'AI 音乐');
const PipelineBoard = lazyTab(() => import('./PipelineBoard.vue'), '作品看板');
const PublishTab = lazyTab(() => import('../tabs/PublishTab.vue'), '全网发行');
const LibraryTab = lazyTab(() => import('../tabs/LibraryTab.vue'), '资产库');
const OpsTab = lazyTab(() => import('../tabs/OpsTab.vue'), '运营台');
import GlobalPlayer from './GlobalPlayer.vue';
import TaskPanel from './TaskPanel.vue';
import AddPersonaModal from './AddPersonaModal.vue';
import EditPersonaModal from './EditPersonaModal.vue';
import PersonaSidebar from './PersonaSidebar.vue';
import CurrentPersonaChip from './CurrentPersonaChip.vue';
import ErrorLogPanel from './ErrorLogPanel.vue';
import ShortcutHelp from './ShortcutHelp.vue';
import Icon from './Icon.vue';

import { setCurrentTab } from '../api';
import { useShortcuts } from '../composables/useShortcuts';
import { useCapabilitiesStore } from '../stores/capabilities';
import { useErrorLogStore } from '../stores/errorLog';
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
const errorLogStore = useErrorLogStore();
const { unreadCount: errorCount } = storeToRefs(errorLogStore);

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

// 把当前路由名同步给 api 层，每次请求会带 X-Client-Tab
// 后端日志按 tab 拆分能一眼看出是哪个屏在打
watch(
  () => route.name,
  (name) => { if (typeof name === 'string') setCurrentTab(name); },
  { immediate: true },
);

const tabs = [
  { name: 'clone', label: '声音克隆', icon: 'clone' },
  { name: 'design', label: '音色设计', icon: 'design' },
  { name: 'dialogue', label: '剧本创作', icon: 'dialogue' },
  { name: 'suno', label: 'AI 音乐', icon: 'suno' },
  { name: 'works', label: '作品看板', icon: 'board' },
  { name: 'publish', label: '全网发行', icon: 'publish' },
  { name: 'library', label: '资产库', icon: 'library' },
  { name: 'ops', label: '运营台', icon: 'pulse' },
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
const sidebarRef = ref(null);
const playerRef = ref(null);
const helpOpen = ref(false);

// 任务面板：从「右下半抽屉」挪到由 header 铃铛开关控制
const taskPanelOpen = ref(false);
const toggleTaskPanel = () => {
  taskPanelOpen.value = !taskPanelOpen.value;
  if (taskPanelOpen.value) {
    taskPanelCollapsed.value = false;
    errorPanelOpen.value = false;
  }
};

// 错误日志面板
const errorPanelOpen = ref(false);
const toggleErrorPanel = () => {
  errorPanelOpen.value = !errorPanelOpen.value;
  if (errorPanelOpen.value) taskPanelOpen.value = false;
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
    { name: '能力状态', action: 'app.loadCaps', fn: () => capabilitiesStore.loadCaps() },
    { name: '模型状态', action: 'app.checkStatus', fn: () => capabilitiesStore.checkStatus() },
    { name: '音色库', action: 'voices.load', fn: () => voicesStore.loadPersonas() },
    { name: '任务队列', action: 'tasks.poll', fn: () => tasksStore.pollTasks() },
  ];
  const results = await Promise.allSettled(jobs.map((j) => j.fn()));
  results.forEach((r, i) => {
    if (r.status === 'rejected') {
      const job = jobs[i];
      tasksStore.reportError(r.reason, { action: job.action, tags: { stage: job.name } });
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

// 全局快捷键
useShortcuts({
  onToggleTaskPanel: () => {
    taskPanelOpen.value = !taskPanelOpen.value;
    if (taskPanelOpen.value) {
      taskPanelCollapsed.value = false;
      errorPanelOpen.value = false;
    }
  },
  onToggleErrorPanel: () => {
    errorPanelOpen.value = !errorPanelOpen.value;
    if (errorPanelOpen.value) taskPanelOpen.value = false;
  },
  onTogglePlayer: () => playerRef.value?.togglePlay(),
  onToggleMute: () => playerRef.value?.toggleMute(),
  onFocusPersonaSearch: () => {
    if (siderCollapsed.value) siderCollapsed.value = false;
    sidebarRef.value?.focusSearch?.();
  },
  onShowHelp: () => { helpOpen.value = true; },
});

/** 把 Suno 后端返回的 ISO 日期格式化成「9/30/2026」 */
const formatRenewDate = (iso) => {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const year = d.getFullYear();
  return `${m}/${day}/${year}`;
};
</script>

<style scoped>
/* 异步组件加载失败的兜底屏。用 :deep 是因为它渲染在 errorComponent 里，
   不在本组件的模板作用域内。 */
:deep(.tab-load-error) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--vf-space-3);
  margin: var(--vf-space-6) 0;
  padding: var(--vf-space-5);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-warn-soft);
  border-left: 3px solid var(--vf-warn);
  border-radius: var(--vf-radius-md);
}
:deep(.tle-title) { margin: 0; font-size: 14px; font-weight: 600; color: var(--vf-text-1); }
:deep(.tle-hint) { margin: 0; font-size: 12px; color: var(--vf-text-2); line-height: 1.7; }
:deep(.tle-btn) {
  background: white;
  border: 1px solid white;
  color: black;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 16px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
}
:deep(.tle-btn:hover) { background: #e4e4e7; border-color: #e4e4e7; }

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

.cap-popover { font-size: 12px; min-width: 220px; }
.cap-pop-row {
  display: flex; gap: var(--vf-space-3); padding: 3px 0;
  align-items: baseline;
}
.cap-pop-k { color: var(--vf-text-3); flex: none; width: 40px; }
.cap-pop-v { color: var(--vf-text-1); }
.cap-pop-v.ok { color: var(--vf-ok); }
.cap-pop-v.off { color: var(--vf-warn); }
.cap-pop-sub {
  color: var(--vf-text-3);
  font-size: 11px;
  margin-left: 2px;
}

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
.bell.has-error {
  border-color: var(--vf-err);
  color: var(--vf-err);
  background: var(--vf-err-soft);
}
.bell-num {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: var(--vf-primary);
  color: white;
  border-radius: var(--vf-radius-full);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 0 2px var(--vf-bg-0);
}
.bell-num.error { background: var(--vf-err); }

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
/*
 * n-tabs 只当「路由 ↔ 当前 tab」的同步源用，它自带的导航条不显示
 * （上面那排手搓的 .tab-nav 才是给人点的，因为 n-tabs 的 tab 只能放文字、
 * 8 个挤一起分不出来）。
 *
 * ⚠️ 只能隐藏**导航条**，不能隐藏整个 .hidden-tabs —— 内容区（n-tab-pane）
 * 就在它里面，一起 display:none 的话八个屏全看不见，页面只剩顶栏、
 * 音色库和那排 tab 按钮，看起来就是「黑屏」「数据没了」。
 */
.hidden-tabs :deep(.n-tabs-nav) {
  display: none;
}
</style>
