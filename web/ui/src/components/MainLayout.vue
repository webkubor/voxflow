<template>
  <n-spin :show="globalLoading" :description="globalLoadingText" size="large" style="min-height: 100vh;">
    <n-layout style="height: 100vh; display: flex; flex-direction: column; position: relative; overflow: hidden;">
      
      <!-- 顶部 Header -->
      <n-layout-header bordered class="app-header">
        <div class="header-left">
          <div class="brand-logo-container">
            <img :src="'/assets/branding/logo-icon.png'" class="logo-img" alt="Logo" />
            <div class="brand-title-wrap">
              <span class="app-title">VoxFlow</span>
              <span class="app-badge">Studio</span>
            </div>
          </div>

          <div class="header-platforms">
            <span class="platforms-label">全网发行网络</span>
            <div class="platform-icons-row">
              <n-tooltip trigger="hover">
                <template #trigger>
                  <div class="platform-badge qishui">
                    <!-- 汽水音乐 SVG -->
                    <svg class="platform-icon" width="20" height="20" viewBox="0 0 58 59" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M57.4495 38.0618H46.4532C46.3514 37.2641 46.1982 36.4738 45.9945 35.6959L40.4963 14.5835H53.9473L50.3335 0.562393H22.4398L28.0185 21.9294C26.534 21.9595 25.0586 22.1679 23.6237 22.5504C20.5394 23.3533 17.7171 24.9471 15.4346 27.1748C13.1521 29.4025 11.4882 32.1873 10.6066 35.2551H21.8199L0.124786 40.9244H9.87519C9.92022 42.3019 10.1177 43.6701 10.4641 45.004C11.5172 49.049 13.914 52.6141 17.2598 55.1123C20.6055 57.6105 24.7008 58.8929 28.8712 58.7483C33.0416 58.6037 37.0386 57.0408 40.2039 54.3168C43.3693 51.5929 45.5143 47.8703 46.2858 43.7621H35.7482L57.4495 38.0618Z" fill="#24FDCF" />
                    </svg>
                  </div>
                </template>
                抖音汽水音乐已就绪
              </n-tooltip>
              
              <n-tooltip trigger="hover">
                <template #trigger>
                  <div class="platform-badge qq">
                    <!-- QQ音乐 SVG -->
                    <svg class="platform-icon" viewBox="-147 -173.3 470 492.3" width="18" height="18" xmlns="http://www.w3.org/2000/svg">
                      <circle cx="88" cy="84" fill="#fbbe0a" r="235"/>
                      <path d="M123.8 104c-5.9-8.3-11.5-16.1-17.1-23.8C85.2 50.4 63.6 20.6 42-9.1 28.3-28 14.7-46.9.8-65.6-3.4-71.2-3.9-77.1-2-83.5c3.9-13.3 13.2-22.5 24.2-30.1 20.1-13.9 42.8-21 66.6-25.2 20.7-3.6 41.2-8 59.3-19.4 4.9-3.1 9-7.3 13.5-11 1.2-1 2.3-2.1 4.6-4.1 1.5 7.3 3 13.4 4 19.5 3 18 1.9 35.5-6.2 52.1-11 22.4-29 36.4-52.6 43.6C97-53.5 82.1-52.4 67-52.5c-1.1 0-2.2.3-4.1.5 3.7 6.5 7 12.6 10.6 18.5 14.5 23.7 29 47.4 43.4 71.2l47.4 78.6c4.1 6.8 8.4 13.6 12.4 20.5 9.3 16 16.1 32.7 14.8 51.9-1.3 18.8-8.1 35.2-19.8 49.6-19.1 23.5-43.9 37.1-73.5 42.4-27.9 4.9-54.5 1.8-79.2-12.3-27.8-15.8-45.6-44.5-41.4-78.7 2.7-22.5 13.9-41.1 30.4-56.4 17.6-16.2 38.5-26.1 61.8-30.6 17.2-3.4 34.4-3.2 51.4 1.4.5.1 1.1-.1 2.6-.1z" fill="#0daf52"/>
                    </svg>
                  </div>
                </template>
                QQ音乐已就绪
              </n-tooltip>

              <n-tooltip trigger="hover">
                <template #trigger>
                  <div class="platform-badge netease">
                    <!-- 网易云音乐 SVG -->
                    <svg class="platform-icon" viewBox="0 0 24 24" width="18" height="18" xmlns="http://www.w3.org/2000/svg">
                      <path fill="#e60026" d="M12.001 22C6.47813 22 2.00098 17.5228 2.00098 12C2.00098 6.47715 6.47813 2 12.001 2C17.5238 2 22.001 6.47715 22.001 12C22.001 17.5228 17.5238 22 12.001 22Z"/>
                    </svg>
                  </div>
                </template>
                网易云音乐已就绪
              </n-tooltip>
            </div>
          </div>
        </div>

        <!-- 顶部右侧：资源与能力状态 -->
        <div class="header-right">
          <n-space size="small" align="center">
            <n-tooltip v-for="c in capBadges" :key="c.key" trigger="hover">
              <template #trigger>
                <div class="status-pill" :class="c.ready ? 'pill-ready' : 'pill-warn'">
                  <span class="status-indicator"></span>
                  <span class="pill-label">{{ c.label }}</span>
                  <span v-if="c.num !== undefined" class="pill-num">{{ c.num }}</span>
                </div>
              </template>
              {{ c.detail || (c.ready ? '服务就绪' : '不可用') }}
            </n-tooltip>
          </n-space>
        </div>
      </n-layout-header>

      <!-- 中部主内容布局 -->
      <n-layout has-sider style="flex: 1; overflow: hidden;">
        <!-- 左侧音色库工坊 (Voice Cast Studio) -->
        <n-layout-sider
          width="320"
          bordered
          content-style="display: flex; flex-direction: column; height: 100%;"
          class="voice-cast-sider"
        >
          <div class="sider-header">
            <div class="sider-title-wrap">
              <span class="sider-title-icon">🎙️</span>
              <h3>音色工坊</h3>
              <span class="sider-count">{{ Object.keys(personas).length }}</span>
            </div>
            <button class="add-persona-btn" @click="showAddPersona = true">
              <span>+ 新建音色</span>
            </button>
          </div>
          
          <div class="sider-content">
            <div 
              v-for="(p, key) in personas" 
              :key="key" 
              class="cast-card"
              :class="{ 
                'is-selected': selectedPersona === key,
                'is-auditioning': previewKey === key
              }"
              @click="selectPersona(key)"
            >
              <!-- 试听波形进度底图 -->
              <div 
                v-if="previewKey === key" 
                class="audition-progress-fill" 
                :style="{ width: previewProgress + '%' }"
              ></div>

              <div class="cast-card-inner">
                <!-- 左侧头像与声波 -->
                <div class="cast-avatar-wrap">
                  <div class="cast-avatar">
                    {{ (p.name || key).charAt(0) }}
                  </div>
                  <!-- 声波跳动微动效 -->
                  <div v-if="previewKey === key" class="cast-wave-pulse">
                    <span></span><span></span><span></span>
                  </div>
                </div>

                <!-- 中间信息 -->
                <div class="cast-info">
                  <div class="cast-name-row">
                    <span class="cast-name">{{ p.name }}</span>
                    <span class="cast-id-pill">{{ key }}</span>
                  </div>
                  <p class="cast-desc">{{ p.desc || p.instruction || '现代 AI 合成声音模版' }}</p>
                  
                  <div class="cast-meta-row">
                    <span class="cast-badge" :class="p.has_audio ? 'badge-audio' : 'badge-no-audio'">
                      {{ p.has_audio ? '● 已装载样音' : '○ 无样音' }}
                    </span>
                  </div>
                </div>

                <!-- 右侧悬浮快捷操作 -->
                <div class="cast-action-hub" @click.stop>
                  <button 
                    v-if="p.has_audio" 
                    class="quick-play-btn" 
                    :class="{ 'btn-playing': previewKey === key }"
                    @click="togglePreview(key)"
                    :title="previewKey === key ? '暂停试听' : '快速试听'"
                  >
                    <svg v-if="previewKey !== key" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                      <path d="M8 5V19L19 12L8 5Z"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                      <path d="M6 19H10V5H6V19ZM14 5V19H18V5H14Z"/>
                    </svg>
                  </button>
                  <button class="mini-edit-btn" @click="openEditPersona(key)" title="编辑配方">✎</button>
                  <button class="mini-del-btn" @click="confirmDeletePersona(key, p)" title="删除音色">🗑️</button>
                </div>
              </div>
            </div>

            <div v-if="Object.keys(personas).length === 0" class="empty-personas">
              <div class="empty-icon">🎧</div>
              <p>暂无音色资产</p>
              <span>点击上方按钮一键克隆或设计专属音色</span>
            </div>
          </div>
        </n-layout-sider>

        <!-- 右侧主创作流媒体大工作区 (Main Studio Hub) -->
        <n-layout-content content-style="padding: 24px; display: flex; flex-direction: column; height: 100%;" class="main-studio-content">
          <n-tabs 
            v-model:value="currentTab" 
            type="line" 
            animated 
            style="height: 100%; display: flex; flex-direction: column;"
            @update:value="switchTab"
          >
            <n-tab-pane name="clone" tab="🎙️ 声音克隆合成">
              <CloneTab />
            </n-tab-pane>
            <n-tab-pane name="design" tab="🎨 提示词音色设计">
              <DesignTab />
            </n-tab-pane>
            <n-tab-pane name="dialogue" tab="📜 剧本多角色创作">
              <DialogueTab />
            </n-tab-pane>
            <n-tab-pane name="suno" tab="⚡ AI 音乐工坊">
              <SunoTab />
            </n-tab-pane>
            <n-tab-pane name="publish" tab="🚀 全网音乐发行">
              <PublishTab />
            </n-tab-pane>
            <n-tab-pane name="library" tab="📁 媒体资产库">
              <LibraryTab />
            </n-tab-pane>
          </n-tabs>
        </n-layout-content>
      </n-layout>

      <!-- 底部播放器 -->
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
  await Promise.all([
    capabilitiesStore.fetchCapabilities(),
    voicesStore.loadPersonas(),
    tasksStore.loadTasks(),
  ]);
  pollTimer = setInterval(() => {
    tasksStore.loadTasks();
  }, 4000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
/* 头部 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.brand-logo-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-img {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  box-shadow: 0 0 16px rgba(129, 140, 248, 0.4);
}

.brand-title-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.app-title {
  font-size: 19px;
  font-weight: 700;
  background: linear-gradient(135deg, #ffffff 30%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.02em;
}

.app-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  background: rgba(129, 140, 248, 0.18);
  color: var(--vf-primary);
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid rgba(129, 140, 248, 0.3);
}

.header-platforms {
  display: flex;
  align-items: center;
  gap: 12px;
  border-left: 1px solid var(--vf-border-subtle);
  padding-left: 20px;
}

.platforms-label {
  font-size: 12px;
  color: var(--vf-text-3);
  font-weight: 500;
}

.platform-icons-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.platform-badge {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.04);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.platform-badge:hover {
  transform: translateY(-2px) scale(1.1);
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--vf-primary);
}

/* 状态胶囊 */
.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 12px;
  font-weight: 500;
  color: var(--vf-text-2);
  transition: all 0.2s ease;
}

.status-pill:hover {
  background: rgba(255, 255, 255, 0.08);
}

.status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.pill-ready .status-indicator {
  background: var(--vf-ok);
  box-shadow: 0 0 8px var(--vf-ok);
}

.pill-warn .status-indicator {
  background: var(--vf-warn);
}

.pill-num {
  font-weight: 700;
  color: var(--vf-primary);
  margin-left: 2px;
}

/* 侧边栏 */
.voice-cast-sider {
  user-select: none;
}

.sider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 20px;
  border-bottom: 1px solid var(--vf-border-subtle);
}

.sider-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sider-title-wrap h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.sider-count {
  font-size: 11px;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.08);
  color: var(--vf-text-2);
  padding: 2px 7px;
  border-radius: 99px;
}

.add-persona-btn {
  background: rgba(129, 140, 248, 0.12);
  border: 1px solid rgba(129, 140, 248, 0.3);
  color: var(--vf-primary);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 99px;
  cursor: pointer;
  transition: all 0.25s ease;
}

.add-persona-btn:hover {
  background: var(--vf-primary);
  color: #ffffff;
  box-shadow: 0 0 14px rgba(129, 140, 248, 0.4);
}

.sider-content {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 流媒体歌手/音色卡片 */
.cast-card {
  position: relative;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--vf-border-subtle);
  border-radius: 16px;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.cast-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.cast-card.is-selected {
  background: rgba(129, 140, 248, 0.12);
  border-color: var(--vf-primary);
  box-shadow: 0 0 20px rgba(129, 140, 248, 0.25), inset 0 0 12px rgba(129, 140, 248, 0.08);
}

.audition-progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, rgba(129, 140, 248, 0.2) 0%, rgba(192, 132, 252, 0.3) 100%);
  pointer-events: none;
  transition: width 0.1s linear;
}

.cast-card-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  position: relative;
  z-index: 1;
}

/* 头像与光圈 */
.cast-avatar-wrap {
  position: relative;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
}

.cast-avatar {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: linear-gradient(135deg, #4f46e5 0%, #818cf8 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 15px;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
}

.cast-wave-pulse {
  position: absolute;
  bottom: -2px;
  right: -2px;
  display: flex;
  gap: 2px;
  background: var(--vf-primary);
  padding: 2px 4px;
  border-radius: 99px;
}

.cast-wave-pulse span {
  width: 2px;
  height: 8px;
  background: #ffffff;
  border-radius: 99px;
  animation: pulse-wave 0.8s infinite alternate ease-in-out;
}
.cast-wave-pulse span:nth-child(2) { animation-delay: 0.2s; height: 12px; }
.cast-wave-pulse span:nth-child(3) { animation-delay: 0.4s; height: 6px; }

@keyframes pulse-wave {
  from { height: 3px; }
  to { height: 12px; }
}

.cast-info {
  flex: 1;
  overflow: hidden;
}

.cast-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}

.cast-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.cast-id-pill {
  font-size: 10px;
  color: var(--vf-text-3);
  font-family: monospace;
  background: rgba(255, 255, 255, 0.05);
  padding: 1px 5px;
  border-radius: 4px;
}

.cast-desc {
  font-size: 11px;
  color: var(--vf-text-2);
  margin: 0 0 6px 0;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.3;
}

.cast-meta-row {
  display: flex;
  align-items: center;
}

.cast-badge {
  font-size: 10px;
  font-weight: 500;
  border-radius: 99px;
}

.badge-audio {
  color: var(--vf-ok);
}

.badge-no-audio {
  color: var(--vf-text-3);
}

/* 快捷操作 */
.cast-action-hub {
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.cast-card:hover .cast-action-hub {
  opacity: 1;
}

.quick-play-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
}

.quick-play-btn:hover {
  background: var(--vf-primary);
  transform: scale(1.1);
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.5);
}

.btn-playing {
  background: var(--vf-primary);
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.4);
}

.mini-edit-btn, .mini-del-btn {
  width: 24px;
  height: 24px;
  background: none;
  border: none;
  color: var(--vf-text-3);
  font-size: 12px;
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.mini-edit-btn:hover { color: var(--vf-text-1); background: rgba(255, 255, 255, 0.08); }
.mini-del-btn:hover { color: var(--vf-err); background: rgba(239, 68, 68, 0.1); }

.empty-personas {
  text-align: center;
  padding: 60px 16px;
  color: var(--vf-text-3);
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-personas p {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--vf-text-2);
}

.empty-personas span {
  font-size: 11px;
  margin-top: 4px;
  display: block;
}
</style>
