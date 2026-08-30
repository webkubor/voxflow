<template>
  <n-spin :show="globalLoading" :description="globalLoadingText" size="large" style="min-height: 100vh;">
    <n-layout style="height: 100vh; display: flex; flex-direction: column;">
      <!-- Header 顶部栏 -->
      <n-layout-header bordered class="app-header">
        <div class="header-left">
          <img :src="'/assets/branding/logo-icon.png'" class="logo-img" alt="Logo" />
          <span class="app-title">VoxFlow 声流</span>
          <div class="header-platforms">
            <span class="platforms-label">一键自动发布：</span>
            <n-space size="small" align="center">
              <n-tooltip trigger="hover">
                <template #trigger>
                  <div class="platform-badge">
                    <!-- 汽水音乐官方彩色 SVG -->
                    <svg class="platform-icon" width="22" height="22" viewBox="0 0 58 59" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <g clip-path="url(#clip0_3409_38666_logo)">
                        <path d="M57.4495 38.0618H46.4532C46.3514 37.2641 46.1982 36.4738 45.9945 35.6959L40.4963 14.5835H53.9473L50.3335 0.562393H22.4398L28.0185 21.9294C26.534 21.9595 25.0586 22.1679 23.6237 22.5504C20.5394 23.3533 17.7171 24.9471 15.4346 27.1748C13.1521 29.4025 11.4882 32.1873 10.6066 35.2551H21.8199L0.124786 40.9244H9.87519C9.92022 42.3019 10.1177 43.6701 10.4641 45.004C11.5172 49.049 13.914 52.6141 17.2598 55.1123C20.6055 57.6105 24.7008 58.8929 28.8712 58.7483C33.0416 58.6037 37.0386 57.0408 40.2039 54.3168C43.3693 51.5929 45.5143 47.8703 46.2858 43.7621H35.7482L57.4495 38.0618Z" fill="url(#paint0_linear_3409_38666_logo)" />
                      </g>
                      <defs>
                        <linearGradient id="paint0_linear_3409_38666_logo" x1="48.2136" y1="2.02163" x2="20.547" y2="55.185" gradientUnits="userSpaceOnUse">
                          <stop stop-color="#FCFB47" />
                          <stop offset="0.1" stop-color="#D2FB46" />
                          <stop offset="0.29" stop-color="#89FC44" />
                          <stop offset="0.45" stop-color="#54FD42" />
                          <stop offset="0.57" stop-color="#33FD41" />
                          <stop offset="0.63" stop-color="#27FD41" />
                          <stop offset="0.75" stop-color="#26FD78" />
                          <stop offset="0.86" stop-color="#25FDA7" />
                          <stop offset="0.95" stop-color="#24FDC4" />
                          <stop offset="1" stop-color="#24FDCF" />
                        </linearGradient>
                        <clipPath id="clip0_3409_38666_logo">
                          <rect width="57.3247" height="58.1771" fill="white" transform="translate(0.124786 0.562393)" />
                        </clipPath>
                      </defs>
                    </svg>
                  </div>
                </template>
                抖音汽水音乐
              </n-tooltip>
              
              <n-tooltip trigger="hover">
                <template #trigger>
                  <div class="platform-badge">
                    <!-- QQ音乐官方彩色 SVG -->
                    <svg class="platform-icon" viewBox="-147 -173.3 470 492.3" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
                      <linearGradient id="qq_linear_logo" gradientTransform="rotate(-90 1397 232)" gradientUnits="userSpaceOnUse" x1="1310" x2="1780" y1="-1077" y2="-1077">
                        <stop offset="0" stop-color="#fbbe0a"/>
                        <stop offset="1" stop-color="#feda24"/>
                      </linearGradient>
                      <circle cx="88" cy="84" fill="url(#qq_linear_logo)" r="235"/>
                      <path d="M123.8 104c-5.9-8.3-11.5-16.1-17.1-23.8C85.2 50.4 63.6 20.6 42-9.1 28.3-28 14.7-46.9.8-65.6-3.4-71.2-3.9-77.1-2-83.5c3.9-13.3 13.2-22.5 24.2-30.1 20.1-13.9 42.8-21 66.6-25.2 20.7-3.6 41.2-8 59.3-19.4 4.9-3.1 9-7.3 13.5-11 1.2-1 2.3-2.1 4.6-4.1 1.5 7.3 3 13.4 4 19.5 3 18 1.9 35.5-6.2 52.1-11 22.4-29 36.4-52.6 43.6C97-53.5 82.1-52.4 67-52.5c-1.1 0-2.2.3-4.1.5 3.7 6.5 7 12.6 10.6 18.5 14.5 23.7 29 47.4 43.4 71.2l47.4 78.6c4.1 6.8 8.4 13.6 12.4 20.5 9.3 16 16.1 32.7 14.8 51.9-1.3 18.8-8.1 35.2-19.8 49.6-19.1 23.5-43.9 37.1-73.5 42.4-27.9 4.9-54.5 1.8-79.2-12.3-27.8-15.8-45.6-44.5-41.4-78.7 2.7-22.5 13.9-41.1 30.4-56.4 17.6-16.2 38.5-26.1 61.8-30.6 17.2-3.4 34.4-3.2 51.4 1.4.5.1 1.1-.1 2.6-.1z" fill="#0daf52"/>
                    </svg>
                  </div>
                </template>
                QQ音乐
              </n-tooltip>

              <n-tooltip trigger="hover">
                <template #trigger>
                  <div class="platform-badge">
                    <!-- 网易云音乐官方红色圆盘 SVG -->
                    <svg class="platform-icon" viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
                      <path fill="#e60026" d="M12.001 22C6.47813 22 2.00098 17.5228 2.00098 12C2.00098 6.47715 6.47813 2 12.001 2C17.5238 2 22.001 6.47715 22.001 12C22.001 17.5228 17.5238 22 12.001 22Z"/>
                      <path d="M10.915 11.5684C11.1559 10.7273 11.9899 10.0266 12.9053 9.9202C13.092 10.6139 13.2926 11.2934 13.4503 11.9826C13.503 12.2127 13.4869 12.4776 13.4317 12.7098C13.2195 13.6019 12.1844 13.9521 11.4543 13.3949C10.9232 12.9896 10.7125 12.2757 10.915 11.5684ZM14.7323 11.3707C14.6071 10.9065 14.476 10.4438 14.3394 9.95097C14.8388 10.081 15.2465 10.3108 15.594 10.6485C16.8506 11.87 16.9793 13.9488 15.888 15.3804C14.7526 16.8698 12.7331 17.5141 10.8596 16.9848C8.55798 16.3345 7.05207 14.0327 7.41861 11.6692C7.69287 9.90076 8.68938 8.66514 10.3187 7.93582C10.7257 7.75367 10.8985 7.37612 10.739 7.0063C10.5818 6.64172 10.1984 6.50242 9.79548 6.66349C7.07384 7.7515 5.47405 10.7974 6.12578 13.6503C6.83792 16.7679 9.61963 18.8125 12.7995 18.5089C14.5318 18.3435 15.9636 17.5609 17.0156 16.1624C18.5218 14.1599 18.3131 11.3794 16.5534 9.66325C15.8867 9.01311 15.0816 8.64501 14.1638 8.50972C14.08 8.49736 13.9463 8.45787 13.9314 8.40426C13.8437 8.09092 13.7506 7.77237 13.7249 7.45035C13.6963 7.09273 14.0143 6.80938 14.3753 6.80488C14.6282 6.80173 14.8087 6.93579 14.9784 7.10468C15.2805 7.40513 15.6824 7.42674 15.9662 7.16733C16.2551 6.90322 16.2624 6.48912 15.984 6.15892C15.4178 5.48746 14.3978 5.26779 13.5545 5.63572C12.7067 6.00566 12.233 6.82256 12.3546 7.72916C12.3922 8.00993 12.4639 8.28616 12.5213 8.57131C12.4302 8.59639 12.3452 8.61951 12.2605 8.64317C11.4048 8.88224 10.6999 9.34675 10.1634 10.0575C9.24196 11.2778 9.22657 12.8846 10.1219 14.0044C11.3962 15.5982 13.8687 15.2882 14.6453 13.4357C14.9287 12.7595 14.9201 12.0676 14.7323 11.3707Z" fill="#ffffff" />
                    </svg>
                  </div>
                </template>
                网易云音乐
              </n-tooltip>
            </n-space>
          </div>
        </div>
        <!--
          能力状态栏：一眼看清「现在能不能干活、还剩多少资源」。

          原来这里只有两个本地模型的「已就绪(未装载)」—— 那是实现细节
          （文件在磁盘 vs 已读进内存），对用户来说都是「能用」，说了等于没说。
          真正该让人看见的是：Suno 还剩多少积分（没了就出不了歌）、
          接的是哪个中台账号、文案助手通不通。
        -->
        <div class="header-right">
          <n-space size="small" align="center">
            <n-tooltip v-for="c in capBadges" :key="c.key" trigger="hover">
              <template #trigger>
                <n-tag :type="c.ready ? 'success' : 'warning'" round size="small" class="cap-tag">
                  <span class="status-dot" :class="c.ready ? 'dot-ready' : 'dot-warn'"></span>
                  {{ c.label }}<em v-if="c.num !== undefined" class="cap-num">{{ c.num }}</em>
                </n-tag>
              </template>
              {{ c.detail || (c.ready ? '正常' : '不可用') }}
            </n-tooltip>
          </n-space>
        </div>
      </n-layout-header>

      <!-- 中部主内容布局 -->
      <n-layout has-sider style="flex: 1; overflow: hidden;">
        <!-- 左侧音色库 Sidebar -->
        <n-layout-sider
          width="280"
          bordered
          content-style="display: flex; flex-direction: column; height: 100%;"
        >
          <div class="sider-header">
            <h3>🎙️ 音色库</h3>
            <n-button type="primary" size="small" @click="showAddPersona = true">
              + 添加音色
            </n-button>
          </div>
          
          <div class="sider-content">
            <div 
              v-for="(p, key) in personas" 
              :key="key" 
              class="persona-card"
              :class="{ 'is-selected': selectedPersona === key }"
              @click="selectPersona(key)"
            >
              <!-- 试听进度背景层 -->
              <div 
                v-if="previewKey === key" 
                class="preview-progress-bg" 
                :style="{ width: previewProgress + '%' }"
              ></div>

              <div class="persona-card-body">
                <div class="persona-title-row">
                  <span class="persona-name">{{ p.name }}</span>
                  <span class="persona-key">{{ key }}</span>
                </div>

                <!-- desc 是人写的描述，instruction 是送给模型的基础指令 ——
                     两回事。以前这里只显示 instruction，于是「描述」这一栏
                     写的其实是技术参数。 -->
                <p class="persona-desc">{{ p.desc || p.instruction || '暂无描述' }}</p>

                <div class="persona-footer-row" @click.stop>
                  <n-space size="small">
                    <n-tag v-if="p.has_audio" type="success" size="small" round>✓ 样音</n-tag>
                    <n-tag v-else type="error" size="small" round>✗ 无样音</n-tag>
                  </n-space>

                  <div class="persona-actions">
                    <n-button
                      v-if="p.has_audio"
                      circle
                      size="tiny"
                      type="primary"
                      secondary
                      @click="togglePreview(key)"
                    >
                      <template #default>
                        {{ previewKey === key ? '⏸' : '▶' }}
                      </template>
                    </n-button>
                    <n-button circle size="tiny" secondary @click="openEditPersona(key)">
                      ✎
                    </n-button>
                    <!-- 这里原来是 v-if="p.source === 'user'"，而后端返回的
                         source 一直是 'registered' —— 条件永不成立，删除按钮
                         从来没出现过。不报错，就是不显示，最难查的那一类。 -->
                    <n-button
                      circle
                      size="tiny"
                      type="error"
                      secondary
                      @click="confirmDeletePersona(key, p)"
                    >
                      🗑️
                    </n-button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="Object.keys(personas).length === 0" class="empty-personas">
              暂无音色，请点击上方按钮添加
            </div>
          </div>
        </n-layout-sider>

        <!-- 右侧主展示区 -->
        <n-layout-content content-style="padding: 20px; display: flex; flex-direction: column; height: 100%;">
          <n-tabs 
            v-model:value="currentTab" 
            type="line" 
            animated 
            style="height: 100%; display: flex; flex-direction: column;"
            @update:value="switchTab"
          >
            <n-tab-pane name="clone" tab="克隆合成">
              <CloneTab />
            </n-tab-pane>
            <n-tab-pane name="design" tab="音色设计">
              <DesignTab />
            </n-tab-pane>
            <n-tab-pane name="dialogue" tab="剧本模式">
              <DialogueTab />
            </n-tab-pane>
            <n-tab-pane name="suno" tab="AI 音乐">
              <SunoTab />
            </n-tab-pane>
            <n-tab-pane name="publish" tab="自动发布">
              <PublishTab />
            </n-tab-pane>
            <n-tab-pane name="library" tab="音频库">
              <LibraryTab />
            </n-tab-pane>
          </n-tabs>
        </n-layout-content>
      </n-layout>

      <!-- 底部播放器 -->
      <GlobalPlayer />

      <!-- 右下角任务抽屉 -->
      <TaskPanel />

      <!-- 添加音色弹窗 -->
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
 * VoxFlow 应用布局。
 * 职责：仅组织布局、选项卡与各领域 store 的初始化轮询。
 * API：状态请求均由 stores/ 中对应领域的 action 发起。
 */
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
import { useSunoStore } from '../stores/suno';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const currentTab = ref('clone');
const showAddPersona = ref(false);
const showEditPersona = ref(false);
const editingKey = ref('');
const capabilitiesStore = useCapabilitiesStore();
const libraryStore = useLibraryStore();
const sunoStore = useSunoStore();
const synthStore = useSynthStore();
const tasksStore = useTasksStore();
const voicesStore = useVoicesStore();
const { capBadges } = storeToRefs(capabilitiesStore);
const { globalLoading, globalLoadingText } = storeToRefs(tasksStore);
const { personas, selectedPersona, previewKey, previewProgress, previewPlayer } = storeToRefs(voicesStore);
const { selectPersona, togglePreview, onPreviewProgress, onPreviewEnded, deletePersona } = voicesStore;

const openEditPersona = (key) => {
  editingKey.value = key;
  showEditPersona.value = true;
};

/**
 * 删音色前问一句。
 *
 * 删的只是 personas.json 里的登记，参考音频文件不动 —— 这一点要在弹窗里
 * 说清楚，否则「删除」看起来像是要把素材一起毁掉，没人敢点。
 */
const confirmDeletePersona = (key, p) => {
  window.$dialog.warning({
    title: `删除音色「${p?.name || key}」？`,
    content: '只删除音色登记，参考音频文件保留在 assets/ 下，之后可以重新注册。',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePersona(key);
        tasksStore.showToast('已删除', 'success');
      } catch (cause) {
        tasksStore.showToast(cause.message || '删除失败', 'error');
      }
    },
  });
};

let statusInterval;
let capsInterval;
let llmInterval;

const runInitialLoads = async () => {
  try {
    await Promise.all([
      capabilitiesStore.checkStatus(),
      capabilitiesStore.loadCaps(),
      capabilitiesStore.checkLLM(),
      voicesStore.loadPersonas(),
      libraryStore.loadAudioList(),
      synthStore.loadScripts(),
      sunoStore.loadSunoStatus(),
    ]);
  } catch (cause) {
    tasksStore.showToast(cause.message || '初始化状态加载失败', 'error');
  }
};

const switchTab = async (tab) => {
  currentTab.value = tab;
  if (tab === 'library') {
    try {
      await libraryStore.loadAudioList();
    } catch (cause) {
      tasksStore.showToast(cause.message || '加载音频库失败', 'error');
    }
  }
};

onMounted(() => {
  void runInitialLoads();
  void tasksStore.pollTasks();
  statusInterval = window.setInterval(() => { void capabilitiesStore.checkStatus().catch(() => {}); }, 10000);
  capsInterval = window.setInterval(() => { void capabilitiesStore.loadCaps().catch(() => {}); }, 30000);
  llmInterval = window.setInterval(() => { void capabilitiesStore.checkLLM().catch(() => {}); }, 30000);
});

onBeforeUnmount(() => {
  tasksStore.stopPolling();
  sunoStore.stopPolling();
  window.clearInterval(statusInterval);
  window.clearInterval(capsInterval);
  window.clearInterval(llmInterval);
});
</script>


<style scoped>
/* 头部样式 */
.cap-tag { font-weight: 500; }
.cap-num { font-style: normal; margin-left: 5px; opacity: .75; font-size: 11px; }
.dot-ready { background: var(--vf-ok); }
.dot-warn { background: var(--vf-warn); }
.app-header {
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  background-color: var(--vf-bg-1);
  box-sizing: border-box;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-img {
  height: 32px;
  width: 32px;
}

.app-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.header-platforms {
  display: flex;
  align-items: center;
  margin-left: 20px;
  border-left: 1px solid var(--vf-border);
  padding-left: 20px;
}

.platforms-label {
  font-size: 11px;
  color: var(--vf-text-3);
  margin-right: 8px;
}

.platform-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s, filter 0.2s;
  filter: grayscale(25%) opacity(80%);
}

.platform-badge:hover {
  transform: translateY(-2px) scale(1.1);
  filter: grayscale(0%) opacity(100%);
}

.model-status-label {
  font-size: 13px;
  color: var(--vf-text-2);
}

.status-tag {
  font-weight: 500;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.dot-green {
  background-color: var(--vf-ok);
}

.dot-orange {
  background-color: var(--vf-gold);
}

.dot-gray {
  background-color: var(--vf-text-3);
}

/* 侧边栏布局 */
.sider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border-bottom: 1px solid var(--vf-bg-4);
}

.sider-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.sider-content {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty-personas {
  text-align: center;
  padding: 40px 10px;
  color: var(--vf-text-3);
  font-size: 13px;
}

/* 音色卡片样式 */
.persona-card {
  position: relative;
  border: 1px solid var(--vf-bg-4);
  border-radius: 6px;
  background-color: var(--vf-bg-1);
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.2s, background-color 0.2s;
}

.persona-card:hover {
  border-color: #4a4a50;
  background-color: var(--vf-bg-3);
}

.persona-card.is-selected {
  border-color: var(--vf-ok);
  background-color: #1c2620;
}

/* 播放进度背景 */
.preview-progress-bg {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background-color: rgba(24, 160, 88, 0.08);
  pointer-events: none;
  transition: width 0.1s linear;
}

.persona-card-body {
  padding: 12px;
  position: relative;
  z-index: 1;
}

.persona-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.persona-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--vf-text-1);
}

.persona-key {
  font-size: 11px;
  color: var(--vf-text-3);
  background-color: rgba(255, 255, 255, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
}

.persona-desc {
  font-size: 12px;
  color: var(--vf-text-2);
  margin: 0 0 10px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
}

.persona-footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.persona-actions {
  display: flex;
  gap: 6px;
}
</style>
