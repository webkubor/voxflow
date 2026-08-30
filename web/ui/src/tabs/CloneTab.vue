<template>
  <div class="tab-content-container">
    <!-- 模型未就绪警告 -->
    <div v-if="!modelStatus.base.ready && !modelStatus.base.downloading" class="warn-banner">
      <span class="warn-icon">⚠️</span>
      <div class="warn-text">
        <strong>Base 基础大模型未就绪</strong> — 请在终端执行 <code>./install.sh</code> 下载模型资产。
      </div>
    </div>

    <!-- 顶部：AI 艺人聚焦展台 (Hero Artist Banner) -->
    <div class="artist-hero-card" :class="{ 'has-selected': !!selectedPersona }">
      <div class="hero-left">
        <div class="hero-avatar">
          {{ selectedPersona ? (personas[selectedPersona]?.name || selectedPersona).charAt(0) : '🎙️' }}
        </div>
        <div class="hero-meta">
          <div class="hero-name-row">
            <span class="hero-title">{{ selectedPersona ? personas[selectedPersona]?.name : '请从左侧选择音色艺人' }}</span>
            <span v-if="selectedPersona" class="hero-id-tag">{{ selectedPersona }}</span>
          </div>
          <p class="hero-subtitle">
            {{ selectedPersona ? (personas[selectedPersona]?.desc || personas[selectedPersona]?.instruction || '已装载专属声音特征矩阵') : '点击左侧音色工坊中的卡片以装载音色' }}
          </p>
        </div>
      </div>

      <div class="hero-right" v-if="selectedPersona">
        <span class="hero-status-tag" :class="personas[selectedPersona]?.has_audio ? 'status-ok' : 'status-warn'">
          {{ personas[selectedPersona]?.has_audio ? '● 样音特征已就绪' : '○ 基础模型模拟' }}
        </span>
      </div>
    </div>

    <!-- AI 写作助手胶囊 -->
    <n-collapse class="ai-help-collapse" :default-expanded-names="[]">
      <n-collapse-item name="ai">
        <template #header>
          <div class="ai-assistant-pill">
            <span class="sparkle-icon">✨</span>
            <span class="assistant-title">AI 灵感写作助手</span>
            <span class="assistant-tip">点击展开让 AI 一键生成优质台词与旁白</span>
          </div>
        </template>
        <AIHelpSection />
      </n-collapse-item>
    </n-collapse>

    <!-- 历史灵感文案库 -->
    <div v-if="savedScripts.length > 0" class="scripts-section">
      <div class="section-header">
        <span class="section-title">📂 灵感草稿箱</span>
        <span class="section-count">{{ savedScripts.length }} 篇</span>
      </div>
      <div class="scripts-list">
        <div 
          v-for="s in savedScripts" 
          :key="s.id" 
          class="script-chip"
          @click="loadScript(s)"
        >
          <span class="chip-icon">📄</span>
          <span class="chip-text">{{ s.title }}</span>
          <button class="chip-del" @click.stop="deleteScript(s.id)">✕</button>
        </div>
      </div>
    </div>

    <!-- 核心创作工作台 (Studio Creation Workspace) -->
    <div class="studio-form-card">
      <div class="workspace-header">
        <span class="workspace-label">📝 声音剧本内容</span>
        <span class="char-counter">{{ cloneForm.text.length }} / 400 字</span>
      </div>

      <div class="textarea-wrapper">
        <n-input 
          v-model:value="cloneForm.text" 
          type="textarea"
          :rows="5"
          maxlength="400"
          placeholder="在此输入需要转成语音的文案，或从上方灵感助手生成..." 
          class="studio-textarea"
        />
      </div>

      <!-- 快速情绪风格标签 (Mood Inspiration Tags) -->
      <div class="mood-tags-row">
        <span class="mood-label">快速氛围预设:</span>
        <div class="mood-pills">
          <button 
            v-for="mood in moodPresets" 
            :key="mood.label"
            class="mood-pill-btn"
            @click="applyMood(mood)"
          >
            {{ mood.label }}
          </button>
        </div>
      </div>

      <!-- 语气与情绪微调 -->
      <div class="params-grid">
        <div class="param-box">
          <label class="param-label">🗣️ 语气与声线特征</label>
          <n-input 
            v-model:value="cloneForm.tone" 
            placeholder="例如：沉稳深情、语速适中（留空则继承音色描述）" 
          />
        </div>
        <div class="param-box">
          <label class="param-label">🎭 情绪控制修饰</label>
          <n-input 
            v-model:value="cloneForm.emotion" 
            placeholder="例如：happy, whispering, excited（留空自动适配）" 
          />
        </div>
      </div>

      <!-- 底部控制与流光生成按钮 (Hero CTA) -->
      <div class="studio-bottom-bar">
        <div class="bottom-left-controls">
          <div class="toggle-control-item">
            <n-switch v-model:value="cloneForm.emotionPriority" size="small" />
            <span class="toggle-text">情绪优先锁定</span>
          </div>
          <button class="save-draft-btn" @click="saveScript">
            <span>💾 存为灵感草稿</span>
          </button>
        </div>

        <div class="bottom-right-actions">
          <button 
            class="hero-generate-btn" 
            :disabled="!selectedPersona || !cloneForm.text.trim()"
            @click="handleSynthesize"
          >
            <span class="btn-spark">⚡</span>
            <span class="btn-text">立即生成高保真音频</span>
          </button>
        </div>
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
const { savedScripts } = storeToRefs(libraryStore);

const cloneForm = reactive({
  text: '',
  tone: '',
  emotion: '',
  emotionPriority: false
});

const moodPresets = [
  { label: '🌿 温柔治愈', tone: '语速轻柔，声线细腻温和', emotion: 'gentle, comforting' },
  { label: '🔥 激情旁白', tone: '情绪饱满，抑扬顿挫富有感染力', emotion: 'excited, dynamic' },
  { label: '🌙 午夜低语', tone: '气声偏多，极具亲近感的耳语', emotion: 'whispering, intimate' },
  { label: '⚔️ 武侠江湖', tone: '苍劲豪迈，带有江湖侠客的洒脱与威严', emotion: 'heroic, calm' }
];

const applyMood = (mood) => {
  cloneForm.tone = mood.tone;
  cloneForm.emotion = mood.emotion;
  tasksStore.showToast(`已应用「${mood.label}」氛围`, 'success');
};

const handleSynthesize = () => {
  if (!selectedPersona.value) {
    tasksStore.showToast('请先在左侧选择要克隆的音色艺人', 'warning');
    return;
  }
  if (!cloneForm.text.trim()) {
    tasksStore.showToast('请输入合成文案', 'warning');
    return;
  }

  synthStore.synthesize({
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
  libraryStore.saveScript(cloneForm.text);
  tasksStore.showToast('已存入灵感草稿箱', 'success');
};

const loadScript = (script) => {
  cloneForm.text = script.content;
  tasksStore.showToast(`已装载「${script.title}」`, 'info');
};

const deleteScript = (id) => {
  libraryStore.deleteScript(id);
};

onMounted(() => {
  libraryStore.loadScripts();
});
</script>

<style scoped>
.tab-content-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1080px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 30px;
}

/* 警告横幅 */
.warn-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 12px 18px;
  border-radius: 14px;
  color: #fca5a5;
  font-size: 13px;
}

.warn-icon { font-size: 18px; }
.warn-text code { background: rgba(0, 0, 0, 0.3); padding: 2px 6px; border-radius: 4px; }

/* 艺人聚焦卡片 (Hero Artist Banner) */
.artist-hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--vf-border-subtle);
  border-radius: 20px;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.artist-hero-card.has-selected {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(192, 132, 252, 0.06) 100%);
  border-color: rgba(129, 140, 248, 0.35);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.hero-avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4f46e5 0%, #a855f7 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: #ffffff;
  box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4);
}

.hero-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hero-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hero-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--vf-text-1);
}

.hero-id-tag {
  font-size: 11px;
  font-family: monospace;
  background: rgba(255, 255, 255, 0.08);
  color: var(--vf-primary-hover);
  padding: 2px 8px;
  border-radius: 6px;
}

.hero-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--vf-text-2);
}

.hero-status-tag {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 99px;
}

.status-ok {
  background: rgba(16, 185, 129, 0.14);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.status-warn {
  background: rgba(245, 158, 11, 0.14);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

/* AI 写作助手 */
.ai-assistant-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.sparkle-icon { font-size: 16px; }
.assistant-title { font-weight: 600; color: var(--vf-text-1); }
.assistant-tip { font-size: 11px; color: var(--vf-text-3); }

/* 灵感草稿箱 */
.scripts-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title { font-size: 12px; font-weight: 600; color: var(--vf-text-2); }
.section-count { font-size: 11px; color: var(--vf-text-3); }

.scripts-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.script-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--vf-border-subtle);
  padding: 4px 12px;
  border-radius: 99px;
  font-size: 12px;
  color: var(--vf-text-2);
  cursor: pointer;
  transition: all 0.2s ease;
}

.script-chip:hover {
  background: rgba(129, 140, 248, 0.12);
  border-color: var(--vf-primary);
  color: var(--vf-text-1);
}

.chip-del {
  background: none;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  font-size: 10px;
  padding: 0;
}

.chip-del:hover { color: var(--vf-err); }

/* 主创作工坊卡片 */
.studio-form-card {
  background: rgba(18, 18, 26, 0.65);
  border: 1px solid var(--vf-border-subtle);
  border-radius: 20px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

.workspace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.workspace-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.char-counter {
  font-size: 12px;
  color: var(--vf-text-3);
  font-family: monospace;
}

.mood-tags-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.mood-label {
  font-size: 12px;
  color: var(--vf-text-3);
}

.mood-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mood-pill-btn {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--vf-border-subtle);
  color: var(--vf-text-2);
  padding: 4px 12px;
  border-radius: 99px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mood-pill-btn:hover {
  background: rgba(129, 140, 248, 0.16);
  border-color: var(--vf-primary);
  color: var(--vf-primary-hover);
  transform: translateY(-1px);
}

.params-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.param-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--vf-text-2);
}

/* 底部操作与流光主生成按钮 */
.studio-bottom-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px solid var(--vf-border-subtle);
}

.bottom-left-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toggle-control-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-text {
  font-size: 12px;
  color: var(--vf-text-2);
}

.save-draft-btn {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--vf-border-subtle);
  color: var(--vf-text-2);
  padding: 6px 14px;
  border-radius: 99px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.save-draft-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--vf-text-1);
}

/* 超大流光主生成按钮 (Suno-like CTA) */
.hero-generate-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 28px;
  border-radius: 99px;
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 50%, #c084fc 100%);
  border: none;
  color: #ffffff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 6px 24px rgba(99, 102, 241, 0.45);
  transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.hero-generate-btn:hover:not(:disabled) {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 8px 32px rgba(129, 140, 248, 0.65);
}

.hero-generate-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.hero-generate-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-spark { font-size: 16px; }
</style>
