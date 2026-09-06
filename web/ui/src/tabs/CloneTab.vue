<template>
  <div class="tab-content-container">
    <!-- 模型未就绪 / 正在下载 -->
    <ModelSetupCard v-if="!modelStatus.base.ready" model="Base" />

    <div class="clone-workbench">
      <!-- 核心工作台卡片 -->
      <section class="studio">
        <!-- 顶栏辅助操作：AI 帮写抽屉开关 + 历史草稿 -->
        <div class="workbench-sub-bar">
          <div class="sub-bar-left">
            <button
              class="tool-tab-btn"
              :class="{ active: showAIHelp }"
              @click="showAIHelp = !showAIHelp"
            >
              <Icon name="sparkles" size="sm" />
              <span>AI 灵感写词</span>
            </button>

            <button
              v-if="savedScripts.length > 0"
              class="tool-tab-btn"
              :class="{ active: showDrafts }"
              @click="showDrafts = !showDrafts"
            >
              <Icon name="library" size="sm" />
              <span>历史草稿 ({{ savedScripts.length }})</span>
            </button>
          </div>

          <span class="studio-counter">{{ cloneForm.text.length }} / 400 字</span>
        </div>

        <!-- 展开的 AI 灵感写词面板 -->
        <div v-if="showAIHelp" class="embedded-tool-panel">
          <div class="embedded-tool-head">
            <span class="embedded-tool-title"><Icon name="sparkles" size="sm" />AI 自动生成台词/旁白</span>
            <button class="close-panel-btn" @click="showAIHelp = false">
              <Icon name="close" size="sm" />
            </button>
          </div>
          <AIHelpSection />
        </div>

        <!-- 展开的草稿箱面板 -->
        <div v-if="showDrafts && savedScripts.length > 0" class="embedded-tool-panel">
          <div class="embedded-tool-head">
            <span class="embedded-tool-title"><Icon name="library" size="sm" />载入历史草稿</span>
            <button class="close-panel-btn" @click="showDrafts = false">
              <Icon name="close" size="sm" />
            </button>
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

        <!-- 核心文案输入 -->
        <div class="form-cell">
          <n-input
            v-model:value="cloneForm.text"
            type="textarea"
            :rows="5"
            maxlength="400"
            show-count
            placeholder="在此输入要合成语音的文本内容（支持 1-400 字）…"
            class="clean-textarea"
          />
        </div>

        <!-- 快捷情感预设 -->
        <div class="mood-bar">
          <span class="mood-label"><Icon name="mask" size="sm" />快捷语气：</span>
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

        <!-- 细化微调参数 -->
        <div class="params-grid">
          <div class="param-cell">
            <label class="param-label"><Icon name="speech" size="sm" />语气描述微调</label>
            <n-input
              v-model:value="cloneForm.tone"
              placeholder="如：沉稳深情、语速适中（留空继承音色描述）"
            />
          </div>
          <div class="param-cell">
            <label class="param-label"><Icon name="mask" size="sm" />情绪标签匹配</label>
            <n-input
              v-model:value="cloneForm.emotion"
              placeholder="如：happy、sad、angry（留空自动适配）"
            />
          </div>
        </div>

        <!-- 底部控制栏 -->
        <div class="studio-footer">
          <div class="footer-left">
            <label class="switch-row">
              <n-switch v-model:value="cloneForm.emotionPriority" size="small" />
              <span>情绪控制优先</span>
            </label>
            <button class="ghost-btn" @click="saveScript">
              <Icon name="save" size="sm" />
              <span>保存为草稿</span>
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
  </div>
</template>

<script setup>
import { reactive, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import AIHelpSection from '../components/AIHelpSection.vue';
import ModelSetupCard from '../components/ModelSetupCard.vue';
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

const showAIHelp = ref(false);
const showDrafts = ref(false);

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
  showDrafts.value = false;
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

.clone-workbench {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
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

/* 顶栏辅助操作区 */
.workbench-sub-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--vf-space-3);
  border-bottom: 1px solid var(--vf-border);
}

.sub-bar-left {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}

.tool-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  font-size: 12px;
  padding: 5px 12px;
  border-radius: var(--vf-radius-full);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}

.tool-tab-btn:hover {
  border-color: var(--vf-border-strong);
  color: var(--vf-text-1);
}

.tool-tab-btn.active {
  background: var(--vf-primary-soft);
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  font-weight: 600;
}

.studio-counter {
  font-size: 11px;
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
}

/* 内嵌浮层小工具面板 */
.embedded-tool-panel {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  padding: var(--vf-space-3) var(--vf-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
  animation: fadeIn 0.15s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.embedded-tool-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.embedded-tool-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.close-panel-btn {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  padding: 2px;
  border-radius: var(--vf-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s;
}

.close-panel-btn:hover {
  color: var(--vf-text-1);
}

/* 草稿箱列表 */
.draft-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--vf-space-2);
}

.draft-chip {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  padding: 3px 4px 3px var(--vf-space-3);
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

.draft-text {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.draft-remove {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  width: 20px;
  height: 20px;
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

/* mood 预设栏 */
.mood-bar {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}

.mood-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--vf-text-3);
  flex: none;
}

.mood-list {
  display: flex;
  gap: var(--vf-space-2);
  flex-wrap: wrap;
}

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

/* params 参数区 */
.params-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vf-space-4);
}

.param-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-label {
  font-size: 12px;
  color: var(--vf-text-2);
}

/* footer 控制区 */
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
  display: inline-flex;
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

@media (max-width: 768px) {
  .params-grid {
    grid-template-columns: 1fr;
  }
}
</style>
