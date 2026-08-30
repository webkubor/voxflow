<template>
  <div class="tab-content-container">
    <!-- 模型未就绪警告 -->
    <div v-if="!modelStatus.base.ready && !modelStatus.base.downloading" class="warn-banner">
      <span class="warn-icon">⚠️</span>
      <div class="warn-text">
        <strong>Base 基础大模型未就绪</strong> — 请在终端运行 <code>./install.sh</code> 下载模型权重。
      </div>
    </div>

    <!-- 顶部：当前音色状态条 -->
    <div class="persona-indicator-bar">
      <div class="indicator-left">
        <span class="indicator-label">当前选定音色:</span>
        <span v-if="selectedPersona" class="indicator-badge">
          🎙️ {{ personas[selectedPersona]?.name || selectedPersona }} ({{ selectedPersona }})
        </span>
        <span v-else class="indicator-none">未选择音色（请点击左侧音色库）</span>
      </div>
      <div class="indicator-right" v-if="selectedPersona">
        <span class="status-chip" :class="personas[selectedPersona]?.has_audio ? 'chip-ok' : 'chip-none'">
          {{ personas[selectedPersona]?.has_audio ? '✓ 样音特征已装载' : '○ 纯文本模拟' }}
        </span>
      </div>
    </div>

    <!-- AI 写作助手折叠条 -->
    <n-collapse class="ai-help-collapse" :default-expanded-names="[]">
      <n-collapse-item name="ai">
        <template #header>
          <div class="ai-collapse-header">
            <span class="spark-icon">✨</span>
            <span class="header-text">AI 帮我写文案</span>
            <span class="header-sub">不会写文案？让 AI 快速生成台词或旁白</span>
          </div>
        </template>
        <AIHelpSection />
      </n-collapse-item>
    </n-collapse>

    <!-- 灵感草稿箱 -->
    <div v-if="savedScripts.length > 0" class="scripts-section">
      <div class="section-title">📂 历史草稿 ({{ savedScripts.length }})</div>
      <div class="scripts-list">
        <div 
          v-for="s in savedScripts" 
          :key="s.id" 
          class="script-chip"
          @click="loadScript(s)"
        >
          <span>{{ s.title }}</span>
          <button class="chip-close" @click.stop="deleteScript(s.id)">✕</button>
        </div>
      </div>
    </div>

    <!-- 核心创作工作台 -->
    <div class="studio-panel">
      <div class="panel-header">
        <span class="panel-title">需要合成的声音文案</span>
        <span class="panel-counter">{{ cloneForm.text.length }} / 400 字</span>
      </div>

      <n-input 
        v-model:value="cloneForm.text" 
        type="textarea"
        :rows="5"
        maxlength="400"
        placeholder="在此输入要合成语音的文本内容..." 
        class="clean-textarea"
      />

      <!-- 快速氛围预设 -->
      <div class="mood-bar">
        <span class="mood-title">快捷预设:</span>
        <div class="mood-list">
          <button 
            v-for="mood in moodPresets" 
            :key="mood.label"
            class="mood-btn"
            @click="applyMood(mood)"
          >
            {{ mood.label }}
          </button>
        </div>
      </div>

      <!-- 参数栅格 -->
      <div class="params-row">
        <div class="param-item">
          <label>🗣️ 语气描述 (音色特征)</label>
          <n-input 
            v-model:value="cloneForm.tone" 
            placeholder="例如：沉稳深情、语速适中（留空继承音色描述）" 
          />
        </div>
        <div class="param-item">
          <label>🎭 情绪标签 (修饰强度)</label>
          <n-input 
            v-model:value="cloneForm.emotion" 
            placeholder="例如：happy、sad、angry（留空自动适配）" 
          />
        </div>
      </div>

      <!-- 底部控制与高对比主按钮 -->
      <div class="panel-footer">
        <div class="footer-left">
          <div class="switch-item">
            <n-switch v-model:value="cloneForm.emotionPriority" size="small" />
            <span>情绪控制优先</span>
          </div>
          <button class="save-btn" @click="saveScript">
            💾 保存草稿
          </button>
        </div>

        <button 
          class="primary-synth-btn" 
          :disabled="!selectedPersona || !cloneForm.text.trim()"
          @click="handleSynthesize"
        >
          立即合成音频
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import AIHelpSection from '../components/AIHelpSection.vue';

import { useCapabilitiesStore } from '../stores/capabilities';
import { useLibraryStore } from '../stores/library';
import { usePipelineStore } from '../stores/pipeline';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const capabilitiesStore = useCapabilitiesStore();
const libraryStore = useLibraryStore();
const pipelineStore = usePipelineStore();
const synthStore = useSynthStore();
const tasksStore = useTasksStore();
const voicesStore = useVoicesStore();

const { modelStatus } = storeToRefs(capabilitiesStore);
const { personas, selectedPersona } = storeToRefs(voicesStore);
// savedScripts / saveScript / deleteScript 都在 synth store。
// library store 管的是音频文件，两回事 —— 指错 store 不会报错，
// 只是点保存没反应，最难查的那类。
const { savedScripts } = storeToRefs(synthStore);

const cloneForm = reactive({
  text: '',
  tone: '',
  emotion: '',
  emotionPriority: false
});

const moodPresets = [
  { label: '温柔治愈', tone: '语速轻柔，声线细腻温和', emotion: 'gentle, comforting' },
  { label: '激情旁白', tone: '情绪饱满，抑扬顿挫富有感染力', emotion: 'excited, dynamic' },
  { label: '午夜低语', tone: '气声偏多，极具亲近感的耳语', emotion: 'whispering, intimate' },
  { label: '武侠江湖', tone: '苍劲豪迈，带有江湖侠客的洒脱与威严', emotion: 'heroic, calm' }
];

const applyMood = (mood) => {
  cloneForm.tone = mood.tone;
  cloneForm.emotion = mood.emotion;
  tasksStore.showToast(`已应用「${mood.label}」`, 'success');
};

const handleSynthesize = () => {
  if (!selectedPersona.value) {
    tasksStore.showToast('请先选择音色', 'warning');
    return;
  }
  if (!cloneForm.text.trim()) {
    tasksStore.showToast('请输入合成文案', 'warning');
    return;
  }

  synthStore.doClone({
    mode: 'clone',
    persona: selectedPersona.value,
    text: cloneForm.text,
    tone: cloneForm.tone,
    emotion: cloneForm.emotion,
    emotion_priority: cloneForm.emotionPriority
  });
};

const saveScript = () => {
  if (!cloneForm.text.trim()) {
    tasksStore.showToast('文案内容为空，无法保存', 'warning');
    return;
  }
  synthStore.saveScript(cloneForm.text);
  tasksStore.showToast('已存入草稿箱', 'success');
};

const loadScript = (script) => {
  cloneForm.text = script.content;
  tasksStore.showToast(`已装载「${script.title}」`, 'info');
};

const deleteScript = (id) => {
  synthStore.deleteScript(id);
};

onMounted(() => {
  synthStore.loadScripts();
});
</script>

<style scoped>
.tab-content-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 40px;
}

/* 警告框 */
.warn-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  padding: 10px 16px;
  border-radius: var(--vf-radius-sm);
  color: var(--vf-warn);
  font-size: 13px;
}

/* 音色指示条 */
.persona-indicator-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
}

.indicator-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.indicator-label {
  font-size: 12px;
  color: var(--vf-text-3);
}

.indicator-badge {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.indicator-none {
  font-size: 13px;
  color: var(--vf-text-3);
}

.status-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--vf-radius-xs);
}
.chip-ok { background: rgba(34, 197, 94, 0.1); color: var(--vf-ok); border: 1px solid rgba(34, 197, 94, 0.2); }
.chip-none { background: var(--vf-bg-3); color: var(--vf-text-3); border: 1px solid var(--vf-border); }

/* AI 助手 */
.ai-collapse-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.spark-icon { font-size: 14px; }
.header-text { font-weight: 600; color: var(--vf-text-1); }
.header-sub { font-size: 11px; color: var(--vf-text-3); }

/* 草稿箱 */
.scripts-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.section-title { font-size: 12px; font-weight: 600; color: var(--vf-text-3); }
.scripts-list { display: flex; flex-wrap: wrap; gap: 6px; }

.script-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  padding: 3px 10px;
  border-radius: var(--vf-radius-xs);
  font-size: 12px;
  color: var(--vf-text-2);
  cursor: pointer;
  transition: all 0.15s ease;
}
.script-chip:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.chip-close {
  background: none;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  font-size: 10px;
  padding: 0;
}
.chip-close:hover { color: var(--vf-err); }

/* 核心工作台 */
.studio-panel {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-title { font-size: 13px; font-weight: 600; color: var(--vf-text-1); }
.panel-counter { font-size: 11px; color: var(--vf-text-3); font-family: monospace; }

.mood-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mood-title { font-size: 12px; color: var(--vf-text-3); }
.mood-list { display: flex; gap: 6px; flex-wrap: wrap; }

.mood-btn {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  font-size: 11px;
  padding: 3px 10px;
  border-radius: var(--vf-radius-xs);
  cursor: pointer;
  transition: all 0.15s ease;
}
.mood-btn:hover {
  background: #ffffff;
  color: #000000;
  border-color: #ffffff;
}

.params-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.param-item { display: flex; flex-direction: column; gap: 5px; }
.param-item label { font-size: 12px; color: var(--vf-text-2); }

.panel-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 14px;
  border-top: 1px solid var(--vf-border);
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.switch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--vf-text-2);
}

.save-btn {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 5px 12px;
  border-radius: var(--vf-radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.save-btn:hover { background: var(--vf-bg-hover); color: var(--vf-text-1); }

/* 高对比主按钮 */
.primary-synth-btn {
  background: #ffffff;
  border: 1px solid #ffffff;
  color: #000000;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 24px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}
.primary-synth-btn:hover:not(:disabled) {
  background: #e4e4e7;
  border-color: #e4e4e7;
  transform: translateY(-1px);
}
.primary-synth-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
