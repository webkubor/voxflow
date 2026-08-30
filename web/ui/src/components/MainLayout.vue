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
                <!-- 用 n-tag 而不是手搓 div+圆点：装了组件库还自己写基础组件，
                     写出来既不统一也不好看，主题切换、尺寸、圆角全要重新对一遍。
                     标签上直接写「这项能力用的是什么」—— 只亮个绿灯写「语音」，
                     四个灯长得一样，看不出跑的是哪个模型、连的是哪个账号。 -->
                <n-tag :type="c.ready ? 'success' : 'warning'" size="small" round :bordered="false">
                  {{ c.label }}
                  <template #icon>
                    <span class="cap-dot" :class="c.ready ? 'on' : 'off'"></span>
                  </template>
                  <span class="cap-what">{{ c.what }}</span>
                  <n-text v-if="c.num !== undefined" depth="3" class="cap-num">{{ c.num }}</n-text>
                </n-tag>
              </template>
              {{ c.detail || (c.ready ? '服务正常' : '未就绪') }}
            </n-tooltip>
          </n-space>
        </div>
        <span class="build-stamp" :title="`前端构建于 ${buildTime}`">{{ buildTime }}</span>
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
            <n-button type="primary" size="tiny" ghost @click="showAddPersona = true">
              + 添加音色
            </n-button>
          </div>
          
          <div class="sider-content">
            <div
              v-for="(p, key) in personas"
              :key="key"
              class="voice-item"
              :class="{ 'is-selected': selectedPersona === key }"
              @click="selectPersona(key)"
            >
              <!-- 试听进度：铺在整张卡底下，不占布局空间 -->
              <div v-if="previewKey === key" class="voice-progress" :style="{ width: previewProgress + '%' }"></div>

              <!-- n-thing 是 naive-ui 的「头像 + 标题 + 描述 + 操作」标准结构，
                   正是这里要的形状。之前手搓了 avatar/name/key/desc/badge/actions
                   六个 div 加一堆 flex，结果名字换行、key 位置错乱、按钮挤成一团。
                   基础结构交给组件库，自己只管品牌相关的那点样式。 -->
              <n-thing>
                <template #avatar>
                  <n-avatar round :size="34" :style="{ background: 'var(--vf-bg-4)', color: 'var(--vf-primary)' }">
                    {{ (p.name || key).charAt(0) }}
                  </n-avatar>
                </template>
                <template #header>
                  <n-ellipsis style="max-width: 128px">{{ p.name || key }}</n-ellipsis>
                </template>
                <template #header-extra>
                  <n-space :size="2" @click.stop>
                    <n-button v-if="p.has_audio" quaternary circle size="tiny"
                              :title="previewKey === key ? '暂停' : '试听'"
                              @click="togglePreview(key)">
                      {{ previewKey === key ? '⏸' : '▶' }}
                    </n-button>
                    <n-button quaternary circle size="tiny" title="编辑" @click="openEditPersona(key)">✎</n-button>
                    <n-button quaternary circle size="tiny" title="删除" @click="confirmDeletePersona(key, p)">✕</n-button>
                  </n-space>
                </template>
                <template #description>
                  <n-ellipsis :line-clamp="2" style="font-size: 11px; color: var(--vf-text-3)">
                    {{ p.desc || p.instruction || '已装载声音特征' }}
                  </n-ellipsis>
                </template>
                <template #footer>
                  <n-space :size="4" align="center">
                    <n-tag size="tiny" :type="p.has_audio ? 'success' : 'warning'" :bordered="false" round>
                      {{ p.has_audio ? '样音已就绪' : '无样音' }}
                    </n-tag>
                    <n-text depth="3" style="font-size: 10px">{{ key }}</n-text>
                  </n-space>
                </template>
              </n-thing>
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
// globalLoading 在 **tasks** store，不在 synth。取错 store 时 storeToRefs
// 给回 undefined，而 n-spin 的 :show 拿到 undefined 就一直转 —— 页面永远在加载中，
// 零报错。今天第三次栽在「方法/状态取错 store」上了。
const { globalLoading, globalLoadingText } = storeToRefs(tasksStore);

// 构建时间戳：刷新后这个数没变，就说明产物没重新构建 ——
// 省掉「改了没效果，先怀疑是不是忘了 build」那一轮
const buildTime = __BUILD_TIME__;

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
    // 模型状态是单独一个端点（/api/status）。上一版漏了这行，于是
    // modelStatus 永远停在初始值 false —— 页面一直显示「Base 大模型未就绪，
    // 请运行 ./install.sh」，而模型明明在磁盘上躺着 8.4 GB。
    // 「该调的没调」比「调错了」更难查：没有报错，只是那块数据永远是默认值。
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



.sider-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 音色卡片：干净利落的高对比面板 */













/* 操作图标 */





.empty-state {
  text-align: center;
  padding: 40px 10px;
  color: var(--vf-text-3);
}
.empty-state p { margin: 0 0 4px 0; font-size: 13px; color: var(--vf-text-2); }
.empty-state span { font-size: 11px; }

.build-stamp {
  margin-left: 12px;
  font-size: 10px;
  color: var(--vf-text-3);
  opacity: .6;
  font-variant-numeric: tabular-nums;
  cursor: default;
}


/* n-tag 里的状态点和副文本。只有这两个是 naive-ui 没有的，
   其余（圆角、配色、尺寸）全交给组件库，不自己写。 */
.cap-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.cap-dot.off { opacity: .5; }
.cap-what { margin-left: 5px; opacity: .75; font-size: 11px; }
.cap-num { margin-left: 4px; font-size: 11px; }

/* 音色卡：只留品牌相关的容器样式，内部结构全交给 n-thing。
   选中态和试听进度条是 naive-ui 没有的，这两个自己写。 */
.voice-item {
  position: relative;
  padding: 10px 12px;
  margin-bottom: 6px;
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg, 14px);
  background: var(--vf-bg-2);
  cursor: pointer;
  overflow: hidden;
  transition: border-color .15s, background .15s;
}
.voice-item:hover { background: var(--vf-bg-3); }
.voice-item.is-selected {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
}
.voice-progress {
  position: absolute;
  left: 0; bottom: 0; height: 2px;
  background: var(--vf-primary);
  transition: width .1s linear;
}
</style>
