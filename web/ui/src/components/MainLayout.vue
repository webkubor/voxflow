<template>
  <n-spin :show="globalLoading" :description="globalLoadingText" size="large" style="min-height: 100vh;">
    <n-layout style="height: 100vh; display: flex; flex-direction: column;">
      <!-- Header 顶部栏 -->
      <n-layout-header bordered class="app-header">
        <div class="header-left">
          <img :src="'/assets/branding/logo-icon.png'" class="logo-img" alt="Logo" />
          <span class="app-title">VoxFlow 声流</span>
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
                  {{ c.label }}<em v-if="c.num" class="cap-num">{{ c.num }}</em>
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
                
                <p class="persona-desc">{{ p.instruction || '暂无描述' }}</p>
                
                <div class="persona-footer-row" @click.stop>
                  <n-space size="small">
                    <n-tag v-if="p.has_ref" type="success" size="mini" round>✓ 样音</n-tag>
                    <n-tag v-else type="error" size="mini" round>✗ 无样音</n-tag>
                  </n-space>
                  
                  <div class="persona-actions">
                    <n-button 
                      v-if="p.has_ref" 
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
                    <n-button 
                      v-if="p.source === 'user'" 
                      circle 
                      size="tiny" 
                      type="error" 
                      secondary
                      @click="deletePersona(key)"
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
            <n-tab-pane name="suno" tab="AI 音乐">
              <SunoTab />
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
 * 核心视图层布局组件
 * 职责：挂载和分发全局状态与逻辑，管理轮询心跳和全局物理元素（样音播放器、全局Loading、弹窗状态）
 * API 来源：/api/status, /api/personas, /api/persona-audio, /api/tasks, /api/suno/status 等
 */
import {ref, reactive, provide, onMounted, onBeforeUnmount, nextTick, computed } from 'vue';

import CloneTab from '../tabs/CloneTab.vue';
import DesignTab from '../tabs/DesignTab.vue';
import SunoTab from '../tabs/SunoTab.vue';
import LibraryTab from '../tabs/LibraryTab.vue';
import GlobalPlayer from './GlobalPlayer.vue';
import TaskPanel from './TaskPanel.vue';
import AddPersonaModal from './AddPersonaModal.vue';

// ── 1. 全局响应式状态 ──
const currentTab = ref('clone');
const personas = ref({});
const selectedPersona = ref(null);
const designPresets = ref([]);

const cloneForm = reactive({
  persona: '',
  text: '',
  tone: '',
  emotion: '',
  emotionPriority: false,
});

const designForm = reactive({
  name: '',
  text: '',
  tone: '',
  emotion: '',
  commit: false,
});

const suno = reactive({
  authenticated: false,
  credits: 0,
  total_credits_left: 0,
  plan: '',
  personas: {},
  submitting: false,
  error: '',
});

const sunoForm = reactive({
  title: '',
  tags: '',
  lyrics: '',
  persona: '',
});

const savedScripts = ref([]);

const llm = reactive({
  available: false,
  checking: false,
  base_url: '',
  models: [],
  genPrompt: '',
  genWordCount: '',
  genLoading: false,
  polStyle: '',
  polLoading: false,
});

const audioFiles = ref([]);

const modelStatus = reactive({
  base: { ready: false, downloading: false, loaded: false, progress: null },
  design: { ready: false, downloading: false, loaded: false, progress: null },
});

const tasks = ref([]);
const prevTaskStatus = {};
const taskPanelCollapsed = ref(false);
let _taskTimer = null;

const player = reactive({
  url: '',
  filename: '',
  visible: false,
});

const previewKey = ref(null);
const previewProgress = ref(0);
const previewPlayer = ref(null);

const globalLoading = ref(false);
const globalLoadingText = ref('');

// ── 2. 状态格式化辅助函数 ──
const getModelStatusType = (st) => {
  if (st.loaded) return 'success';
  if (st.downloading) return 'warning';
  return 'default';
};

const getModelStatusDotClass = (st) => {
  if (st.loaded) return 'dot-green';
  if (st.downloading) return 'dot-orange animate-pulse';
  return 'dot-gray';
};

const getModelStatusText = (st) => {
  if (st.loaded) return '已装载';
  if (st.downloading) return `下载中 ${st.progress}%`;
  if (st.ready) return '已就绪 (未装载)';
  return '未就绪';
};

// ── 3. 全局核心方法 ──

const showToast = (msg, type = 'info') => {
  if (!window.$message) {
    console.log(`[Toast Fallback] [${type}] ${msg}`);
    return;
  }
  if (type === 'success') window.$message.success(msg);
  else if (type === 'error') window.$message.error(msg);
  else if (type === 'warning') window.$message.warning(msg);
  else window.$message.info(msg);
};

const showLoading = (text) => {
  globalLoadingText.value = text;
  globalLoading.value = true;
};

const hideLoading = () => {
  globalLoading.value = false;
  globalLoadingText.value = '';
};

// 切换选项卡
const switchTab = (tab) => {
  currentTab.value = tab;
  if (tab === 'library') {
    loadAudioList();
  }
};

// 模型与系统状态自检
/**
 * 能力状态：本地模型 / Suno 积分 / 中台身份 / 文案助手。
 * 走后端聚合的 /api/capabilities —— 前端不必并发调四个接口各自处理失败，
 * 也不必自己拼「能不能开工」这个判断。
 */
const caps = ref({});
const capBadges = computed(() => {
  const c = caps.value || {};
  return [
    { key: 'tts',    label: '语音',   ready: !!c.tts?.ready,    detail: c.tts?.detail },
    { key: 'suno',   label: 'Suno',   ready: !!c.suno?.ready,   detail: c.suno?.detail, num: c.suno?.credits },
    { key: 'studio', label: '中台',   ready: !!c.studio?.ready, detail: c.studio?.detail },
    { key: 'llm',    label: '文案',   ready: !!c.llm?.ready,    detail: c.llm?.detail },
  ];
});
const loadCaps = async () => {
  try {
    const r = await fetch('/api/capabilities');
    caps.value = await r.json();
  } catch { /* 拿不到就保持上一次的状态，不要闪成全红 */ }
};

const checkStatus = async () => {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    modelStatus.base = {
      ready: !!data.base_model,
      downloading: !!data.base_downloading,
      loaded: !!data.base_loaded,
      progress: data.base_progress?.percent || 0
    };
    modelStatus.design = {
      ready: !!data.design_model,
      downloading: !!data.design_downloading,
      loaded: !!data.design_loaded,
      progress: data.design_progress?.percent || 0
    };
  } catch (e) {
    console.error('获取系统状态失败:', e);
  }
};

// 获取音色列表
const loadPersonas = async () => {
  try {
    const res = await fetch('/api/personas');
    const data = await res.json();
    personas.value = data.personas || {};
    designPresets.value = data.presets || [];
    
    // 如果没有选中音色且列表有数据，默认选中第一个
    const keys = Object.keys(personas.value);
    if (keys.length > 0 && !selectedPersona.value) {
      selectPersona(keys[0]);
    }
  } catch (e) {
    showToast('获取音色列表失败', 'error');
  }
};

// 选中音色
const selectPersona = (key) => {
  selectedPersona.value = key;
  cloneForm.persona = key;
  const p = personas.value[key];
  if (p && p.instruction) {
    cloneForm.tone = p.instruction;
  }
};

// 删除自定义音色
const deletePersona = (key) => {
  if (!window.$dialog) {
    console.warn('dialog api 暂未加载');
    return;
  }
  window.$dialog.warning({
    title: '确认删除',
    content: `确定要删除自定义音色 "${personas.value[key]?.name || key}" 吗？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      showLoading('正在删除音色...');
      try {
        const res = await fetch(`/api/personas/${key}`, { method: 'DELETE' });
        const data = await res.json();
        hideLoading();
        if (data.status === 'ok') {
          showToast('删除音色成功', 'success');
          if (selectedPersona.value === key) {
            selectedPersona.value = null;
            cloneForm.persona = '';
          }
          await loadPersonas();
        } else {
          showToast(data.error || '删除失败', 'error');
        }
      } catch (e) {
        hideLoading();
        showToast('删除音色网络错误', 'error');
      }
    }
  });
};

// 试听左侧音色预览
const togglePreview = (key) => {
  if (previewKey.value === key) {
    // 暂停
    previewPlayer.value.pause();
    previewKey.value = null;
    previewProgress.value = 0;
  } else {
    // 播放
    previewKey.value = key;
    previewPlayer.value.src = `/api/persona-audio?key=${key}`;
    previewPlayer.value.load();
    previewPlayer.value.play().catch((err) => {
      showToast('样音播放失败或不存在', 'error');
      previewKey.value = null;
      previewProgress.value = 0;
    });
    
    // 同步选中
    selectPersona(key);
  }
};

const onPreviewProgress = () => {
  if (previewPlayer.value && previewPlayer.value.duration) {
    previewProgress.value = (previewPlayer.value.currentTime / previewPlayer.value.duration) * 100;
  }
};

const onPreviewEnded = () => {
  previewKey.value = null;
  previewProgress.value = 0;
};

// 载入生成音频列表
const loadAudioList = async () => {
  try {
    const res = await fetch('/api/audio-list');
    const data = await res.json();
    audioFiles.value = data.files || [];
  } catch (e) {
    showToast('获取音频库列表失败', 'error');
  }
};

// 物理删除音频
const deleteAudio = (filename) => {
  dialog.warning({
    title: '确认删除',
    content: `确定要物理删除该音频吗？该操作不可逆。`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const res = await fetch(`/api/audio/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast('音频删除成功', 'success');
          if (player.filename === filename) {
            player.visible = false;
            player.url = '';
            player.filename = '';
          }
          await loadAudioList();
        } else {
          showToast(data.error || '删除失败', 'error');
        }
      } catch (e) {
        showToast('物理删除音频网络错误', 'error');
      }
    }
  });
};

// 文案库加载
const loadScripts = async () => {
  try {
    const res = await fetch('/api/scripts');
    const data = await res.json();
    savedScripts.value = data.scripts || [];
  } catch (e) {
    console.error('加载文案历史失败:', e);
  }
};

// 载入单个文案
const loadScript = (script) => {
  cloneForm.text = script.content;
  showToast('已载入选中文案', 'success');
};

// 保存当前文案
const saveScript = async () => {
  if (!cloneForm.text.trim()) {
    showToast('文本框内容不能为空', 'warning');
    return;
  }
  const title = cloneForm.text.trim().substring(0, 15);
  try {
    const res = await fetch('/api/scripts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content: cloneForm.text }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast('保存文案成功', 'success');
      savedScripts.value = data.scripts || [];
    } else {
      showToast(data.error || '保存失败', 'error');
    }
  } catch (e) {
    showToast('保存文案网络异常', 'error');
  }
};

// 删除文案
const deleteScript = async (id) => {
  try {
    const res = await fetch(`/api/scripts/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast('文案已删除', 'success');
      savedScripts.value = data.scripts || [];
    } else {
      showToast(data.error || '删除文案失败', 'error');
    }
  } catch (e) {
    showToast('删除文案网络错误', 'error');
  }
};

// 检查 LLM 文案助手状态
const checkLLM = async () => {
  llm.checking = true;
  try {
    const res = await fetch('/api/llm/status');
    const data = await res.json();
    llm.available = !!data.available;
    llm.base_url = data.base_url || '';
    llm.models = data.models || [];
  } catch (e) {
    llm.available = false;
  } finally {
    llm.checking = false;
  }
};

// AI 文案生成
const aiGenerate = async () => {
  if (!llm.genPrompt.trim()) {
    showToast('请填写提示词', 'warning');
    return;
  }
  llm.genLoading = true;
  try {
    const res = await fetch('/api/llm/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: llm.genPrompt,
        word_count: parseInt(llm.genWordCount) || 100
      }),
    });
    const data = await res.json();
    if (data.text) {
      cloneForm.text = data.text;
      showToast('✨ 文案生成成功', 'success');
    } else {
      showToast(data.error || '生成失败', 'error');
    }
  } catch (e) {
    showToast('AI生成接口请求异常', 'error');
  } finally {
    llm.genLoading = false;
  }
};

// AI 文案润色
const aiPolish = async () => {
  if (!cloneForm.text.trim()) {
    showToast('文本框中没有可以润色的文案', 'warning');
    return;
  }
  llm.polLoading = true;
  try {
    const res = await fetch('/api/llm/polish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: cloneForm.text,
        style: llm.polStyle || '自然有亲和力'
      }),
    });
    const data = await res.json();
    if (data.text) {
      cloneForm.text = data.text;
      showToast('✨ 文案润色成功', 'success');
    } else {
      showToast(data.error || '润色失败', 'error');
    }
  } catch (e) {
    showToast('AI润色接口请求异常', 'error');
  } finally {
    llm.polLoading = false;
  }
};

// 提交声音克隆任务
const doClone = async () => {
  if (!cloneForm.persona) {
    showToast('请选择音色', 'warning');
    return;
  }
  if (!cloneForm.text.trim()) {
    showToast('请填写需要合成的文案', 'warning');
    return;
  }
  if (cloneForm.text.length > 400) {
    showToast('合成文本字数不能超过400字', 'warning');
    return;
  }

  showLoading('正在提交克隆任务...');
  try {
    const res = await fetch('/api/clone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        persona: cloneForm.persona,
        text: cloneForm.text,
        tone: cloneForm.tone,
        emotion: cloneForm.emotion,
        emotion_priority: cloneForm.emotionPriority,
      }),
    });
    const data = await res.json();
    hideLoading();
    if (data.task_id) {
      showToast('克隆任务提交成功！', 'success');
      taskPanelCollapsed.value = false;
      pollTasks();
    } else {
      showToast(data.error || '提交失败', 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('克隆请求接口异常', 'error');
  }
};

// 提交音色设计任务
const doDesign = async () => {
  if (!designForm.name.trim()) {
    showToast('请填写音色名称', 'warning');
    return;
  }
  if (!designForm.text.trim()) {
    showToast('请填写建模短句', 'warning');
    return;
  }

  showLoading('正在提交音色设计...');
  try {
    const res = await fetch('/api/design', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        voice_name: designForm.name,
        text: designForm.text,
        tone: designForm.tone,
        emotion: designForm.emotion,
        commit: designForm.commit,
      }),
    });
    const data = await res.json();
    hideLoading();
    if (data.task_id) {
      showToast('音色设计任务提交成功！', 'success');
      taskPanelCollapsed.value = false;
      pollTasks();
    } else {
      showToast(data.error || '提交设计失败', 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('提交设计接口异常', 'error');
  }
};

// 全局播放器控制
const playAudio = (url, filename) => {
  player.url = url;
  player.filename = filename;
  player.visible = true;
};

// 取消/删除任务
const cancelTask = async (taskId) => {
  try {
    const res = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast('任务已取消', 'success');
      await pollTasks();
    } else {
      showToast(data.error || '取消失败', 'error');
    }
  } catch (e) {
    showToast('取消任务接口异常', 'error');
  }
};

// 任务队列轮询
const pollTasks = async () => {
  if (_taskTimer) clearTimeout(_taskTimer);
  try {
    const res = await fetch('/api/tasks');
    const data = await res.json();
    const newTasks = data.tasks || [];
    
    // 检测状态变化触发自动试听与刷新
    for (const t of newTasks) {
      const prevStatus = prevTaskStatus[t.id];
      if (prevStatus && prevStatus !== t.status) {
        if (t.status === 'done') {
          showToast(`任务 [${t.type === 'clone' ? '声音克隆' : '音色设计'}] 完成！`, 'success');
          // 自动播放
          if (t.result && t.result.urls && t.result.urls.length > 0) {
            playAudio(t.result.urls[0], t.result.files[0]);
          }
          // 刷新列表
          loadAudioList();
          if (t.result && t.result.committed) {
            loadPersonas();
          }
        } else if (t.status === 'error') {
          showToast(`任务 [${t.type === 'clone' ? '声音克隆' : '音色设计'}] 失败: ${t.error || ''}`, 'error');
        }
      }
      prevTaskStatus[t.id] = t.status;
    }

    tasks.value = newTasks;
    
    // 是否还有正在排队或执行中的任务
    const hasActive = newTasks.some(x => x.status === 'queued' || x.status === 'running');
    const interval = hasActive ? 1500 : 5000;
    
    _taskTimer = setTimeout(pollTasks, interval);
  } catch (e) {
    // 网络错误静默降级为5秒重试
    _taskTimer = setTimeout(pollTasks, 5000);
  }
};

// ── Suno AI 音乐相关 ──
const loadSunoStatus = async () => {
  try {
    const res = await fetch('/api/suno/status');
    const data = await res.json();
    suno.authenticated = !!data.authenticated;
    suno.credits = data.credits || 0;
    suno.total_credits_left = data.total_credits_left || 0;
    suno.plan = data.plan || '';
    suno.personas = data.personas || {};
  } catch (e) {
    suno.error = '获取 Suno 状态失败';
  }
};

const submitSuno = async () => {
  if (!sunoForm.title.trim()) {
    showToast('请填写歌曲标题', 'warning');
    return;
  }
  suno.submitting = true;
  suno.error = '';
  try {
    const res = await fetch('/api/suno/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sunoForm),
    });
    const data = await res.json();
    if (!data.task_id) {
      suno.error = data.error || '提交失败';
      suno.submitting = false;
      return;
    }
    showToast('🎵 音乐生成已提交，完成后进音频库', 'success');
    suno.submitting = false;
    pollSunoTask(data.task_id);
  } catch (e) {
    suno.error = '提交失败: ' + e.message;
    suno.submitting = false;
  }
};

const pollSunoTask = async (taskId) => {
  const check = async () => {
    try {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      const t = (data.tasks || []).find(x => x.id === taskId);
      if (!t) return;
      if (t.status === 'done' || t.status === 'error') {
        suno.submitting = false;
        if (t.status === 'done') {
          showToast('🎵 Suno 音乐生成完成！', 'success');
          loadAudioList();
          if (t.result && t.result.urls && t.result.urls.length) {
            playAudio(t.result.urls[0], t.result.files[0]);
          }
        } else {
          suno.error = t.error || '生成失败';
        }
      } else {
        setTimeout(check, 5000);
      }
    } catch (e) {
      setTimeout(check, 5000);
    }
  };
  setTimeout(check, 3000);
};

// ── 4. 依赖注入 SSOT 共享 ──
provide('state', {
  currentTab,
  personas,
  selectedPersona,
  designPresets,
  cloneForm,
  designForm,
  suno,
  sunoForm,
  savedScripts,
  llm,
  audioFiles,
  modelStatus,
  tasks,
  taskPanelCollapsed,
  player,
  previewKey,
  previewProgress,
});

provide('actions', {
  selectPersona,
  togglePreview,
  loadAudioList,
  deleteAudio,
  loadScript,
  saveScript,
  deleteScript,
  checkLLM,
  aiGenerate,
  aiPolish,
  doClone,
  doDesign,
  cancelTask,
  playAudio,
  loadSunoStatus,
  submitSuno,
  loadPersonas,
  showToast,
  showLoading,
  hideLoading
});

// ── 5. 生命周期挂载 ──
onMounted(() => {
  checkStatus();
  loadCaps();
  loadPersonas();
  loadAudioList();
  loadScripts();
  checkLLM();
  loadSunoStatus();
  pollTasks();
  
  // 定时心跳轮询
  window._statusInterval = setInterval(checkStatus, 10000);
  // 能力状态变化慢（积分、登录态），30 秒够了 —— 太频繁会撞中台限流
  window._capsInterval = setInterval(loadCaps, 30000);
  window._llmInterval = setInterval(checkLLM, 30000);
});

onBeforeUnmount(() => {
  if (_taskTimer) clearTimeout(_taskTimer);
  if (window._statusInterval) clearInterval(window._statusInterval);
  if (window._llmInterval) clearInterval(window._llmInterval);
});
</script>

<style scoped>
/* 头部样式 */
.cap-tag { font-weight: 500; }
.cap-num { font-style: normal; margin-left: 5px; opacity: .75; font-size: 11px; }
.dot-ready { background: #63e2b7; }
.dot-warn { background: #f2c97d; }
.app-header {
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  background-color: #18181c;
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
  color: #fff;
}

.model-status-label {
  font-size: 13px;
  color: #a0a0a5;
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
  background-color: #18a058;
}

.dot-orange {
  background-color: #f0a020;
}

.dot-gray {
  background-color: #707075;
}

/* 侧边栏布局 */
.sider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border-bottom: 1px solid #2d2d30;
}

.sider-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #e5e5e7;
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
  color: #707075;
  font-size: 13px;
}

/* 音色卡片样式 */
.persona-card {
  position: relative;
  border: 1px solid #2d2d30;
  border-radius: 6px;
  background-color: #18181c;
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.2s, background-color 0.2s;
}

.persona-card:hover {
  border-color: #4a4a50;
  background-color: #1e1e24;
}

.persona-card.is-selected {
  border-color: #36ad6a;
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
  color: #fff;
}

.persona-key {
  font-size: 11px;
  color: #808085;
  background-color: rgba(255, 255, 255, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
}

.persona-desc {
  font-size: 12px;
  color: #a0a0a5;
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
