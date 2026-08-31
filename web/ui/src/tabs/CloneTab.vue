<template>
  <div class="tab-content-container">
    <!-- 模型未就绪 / 正在下载 -->
    <WarnBanner
      v-if="!modelStatus.base.ready && !modelStatus.base.downloading"
      type="warn"
      title="Base 基础大模型未就绪"
      hint="请在终端运行 ./install.sh 下载模型权重，下载完成后此警告会自动消失。"
    />

    <!-- AI 助手折叠 -->
    <n-collapse class="ai-collapse" :default-expanded-names="[]">
      <n-collapse-item name="ai">
        <template #header>
          <div class="ai-header">
            <Icon name="sparkles" size="sm" />
            <span class="ai-title">AI 帮我写文案</span>
            <span class="ai-sub">不会写文案？让 AI 快速生成台词或旁白</span>
          </div>
        </template>
        <AIHelpSection />
      </n-collapse-item>
    </n-collapse>

    <!-- 草稿箱 -->
    <div v-if="savedScripts.length > 0" class="drafts-section">
      <div class="section-title">
        <Icon name="library" size="sm" />
        <span>历史草稿</span>
        <span class="section-count">{{ savedScripts.length }}</span>
      </div>
      <div class="draft-list">
        <div
          v-for="s in savedScripts"
          :key="s.id"
          class="draft-chip"
          @click="loadScript(s)"
        >
          <span class="draft-text">{{ s.title }}</span>
          <button class="draft-remove" title="删除草稿" @click.stop="deleteScript(s.id)">
            <Icon name="close" size="sm" />
          </button>
        </div>
      </div>
    </div>

    <!-- 核心工作台 -->
    <section class="studio">
      <div class="studio-head">
        <span class="studio-title">需要合成的声音文案</span>
        <span class="studio-counter">{{ cloneForm.text.length }} / 400 字</span>
      </div>

      <n-input
        v-model:value="cloneForm.text"
        type="textarea"
        :rows="6"
        maxlength="400"
        show-count
        placeholder="在此输入要合成语音的文本内容…"
        class="clean-textarea"
      />

      <!-- 快捷预设 -->
      <div class="mood-bar">
        <span class="mood-label">快捷预设</span>
        <div class="mood-list">
          <button
            v-for="mood in moodPresets"
            :key="mood.label"
            class="mood-chip"
            :class="{ active: activeMood === mood.label }"
            @click="toggleMood(mood)"
          >
            {{ mood.label }}
          </button>
        </div>
      </div>

      <!-- 参数 -->
      <div class="params-grid">
        <div class="param-cell">
          <label class="param-label">🗣️ 语气描述</label>
          <n-input
            v-model:value="cloneForm.tone"
            placeholder="如：沉稳深情、语速适中（留空继承音色描述）"
          />
        </div>
        <div class="param-cell">
          <label class="param-label">🎭 情绪标签</label>
          <n-input
            v-model:value="cloneForm.emotion"
            placeholder="如：happy、sad、angry（留空自动适配）"
          />
        </div>
      </div>

      <!-- 底部控制 -->
      <div class="studio-footer">
        <div class="footer-left">
          <label class="switch-row">
            <n-switch v-model:value="cloneForm.emotionPriority" size="small" />
            <span>情绪控制优先</span>
          </label>
          <button class="ghost-btn" @click="saveScript">
            <Icon name="library" size="sm" />
            <span>保存草稿</span>
          </button>
        </div>
        <button
          class="primary-btn"
          :disabled="!selectedPersona || !cloneForm.text.trim()"
          @click="handleSynthesize"
        >
          <Icon name="play" size="sm" />
          <span>立即合成音频</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { toMessage } from '../api';
import AIHelpSection from '../components/AIHelpSection.vue';
import WarnBanner from '../components/WarnBanner.vue';
import Icon from '../components/Icon.vue';

import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const capabilitiesStore = useCapabilitiesStore();
const synthStore = useSynthStore();
const tasksStore = useTasksStore();
const voicesStore = useVoicesStore();

const { modelStatus } = storeToRefs(capabilitiesStore);
const { selectedPersona } = storeToRefs(voicesStore);
const { savedScripts } = storeToRefs(synthStore);

const cloneForm = reactive({
  text: '',
  tone: '',
  emotion: '',
  emotionPriority: false,
});

const moodPresets = [
  { label: '温柔治愈', tone: '语速轻柔，声线细腻温和', emotion: 'gentle, comforting' },
  { label: '激情旁白', tone: '情绪饱满，抑扬顿挫富有感染力', emotion: 'excited, dynamic' },
  { label: '午夜低语', tone: '气声偏多，极具亲近感的耳语', emotion: 'whispering, intimate' },
  { label: '武侠江湖', tone: '苍劲豪迈，带有江湖侠客的洒脱与威严', emotion: 'heroic, calm' },
];
const activeMood = ref('');

const toggleMood = (mood) => {
  if (activeMood.value === mood.label) {
    activeMood.value = '';
    cloneForm.tone = '';
    cloneForm.emotion = '';
    tasksStore.showToast(`已取消「${mood.label}」`, 'info');
  } else {
    activeMood.value = mood.label;
    cloneForm.tone = mood.tone;
    cloneForm.emotion = mood.emotion;
    tasksStore.showToast(`已应用「${mood.label}」`, 'success');
  }
};

const handleSynthesize = () => {
  if (!selectedPersona.value) return tasksStore.showToast('请先选择音色', 'warning');
  if (!cloneForm.text.trim()) return tasksStore.showToast('请输入合成文案', 'warning');
  synthStore.doClone({
    mode: 'clone',
    persona: selectedPersona.value,
    text: cloneForm.text,
    tone: cloneForm.tone,
    emotion: cloneForm.emotion,
    emotion_priority: cloneForm.emotionPriority,
  });
};

const saveScript = async () => {
  if (!cloneForm.text.trim()) return tasksStore.showToast('文案内容为空，无法保存', 'warning');
  try {
    await synthStore.saveScript(cloneForm.text);
    tasksStore.showToast('已存入草稿箱', 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'script.save' });
  }
};

const loadScript = (script) => {
  cloneForm.text = script.content;
  tasksStore.showToast(`已装载「${script.title}」`, 'info');
};

const deleteScript = (id) => synthStore.deleteScript(id);

onMounted(() => synthStore.loadScripts());
</script>

<style scoped>
.tab-content-container {
  max-width: 1080px;
  margin: 0 auto;
}

/* AI 助手 */
.ai-collapse {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  overflow: hidden;
}
:deep(.ai-collapse .n-collapse-item__header-main) {
  width: 100%;
}
.ai-header {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
}
.ai-title { font-weight: 600; color: var(--vf-text-1); }
.ai-sub { font-size: 11px; color: var(--vf-text-3); margin-left: var(--vf-space-2); }

/* 草稿箱 */
.drafts-section { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.section-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-3);
}
.section-count {
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
  font-size: 11px;
}
.draft-list { display: flex; flex-wrap: wrap; gap: var(--vf-space-2); }
.draft-chip {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  padding: 4px 4px 4px var(--vf-space-3);
  border-radius: var(--vf-radius-full);
  font-size: 12px;
  color: var(--vf-text-2);
  cursor: pointer;
  transition: all 0.15s;
}
.draft-chip:hover {
  background: var(--vf-bg-hover);
  border-color: var(--vf-border-strong);
  color: var(--vf-text-1);
}
.draft-text { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.draft-remove {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.draft-remove:hover {
  background: var(--vf-err-soft);
  color: var(--vf-err);
}

/* 核心工作台 */
.studio {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}

.studio-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.studio-title { font-size: 13px; font-weight: 600; color: var(--vf-text-1); }
.studio-counter {
  font-size: 11px;
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
}

/* mood */
.mood-bar {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}
.mood-label {
  font-size: 12px;
  color: var(--vf-text-3);
  flex: none;
}
.mood-list { display: flex; gap: var(--vf-space-2); flex-wrap: wrap; }
.mood-chip {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: var(--vf-radius-full);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.mood-chip:hover {
  border-color: var(--vf-border-strong);
  color: var(--vf-text-1);
}
.mood-chip.active {
  background: var(--vf-primary-soft);
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  font-weight: 600;
}

/* params */
.params-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vf-space-4);
}
.param-cell { display: flex; flex-direction: column; gap: 6px; }
.param-label { font-size: 12px; color: var(--vf-text-2); }

/* footer */
.studio-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: var(--vf-space-4);
  border-top: 1px solid var(--vf-border);
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}
.footer-left {
  display: flex;
  align-items: center;
  gap: var(--vf-space-4);
}
.switch-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  color: var(--vf-text-2);
  cursor: pointer;
}

.ghost-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 6px 12px;
  border-radius: var(--vf-radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.ghost-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: white;
  border: 1px solid white;
  color: black;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 18px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.primary-btn:hover:not(:disabled) {
  background: #e4e4e7;
  border-color: #e4e4e7;
  transform: translateY(-1px);
}
.primary-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
