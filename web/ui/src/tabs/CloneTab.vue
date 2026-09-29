<template>
  <div class="tab-content-container">
    <!-- 模型未就绪 / 正在下载 -->
    <ModelSetupCard v-if="!modelStatus.base.ready" model="Base" />

    <!-- 顶层流程指引 -->
    <div class="clone-flow-banner">
      <div class="banner-left">
        <Icon name="voice" size="sm" />
        <div class="banner-text-group">
          <span class="banner-title">声音工坊 · 文本配音：选定声线角色，一键口播朗读</span>
          <span class="banner-desc">在左侧挑选已入库的声音角色，输入台词与语气描述，即刻生成广播级品质旁白与配音音频。</span>
        </div>
      </div>
      <div class="banner-right">
        <button class="goto-design-btn" @click="goToDesign">
          <Icon name="sparkles" size="sm" />
          <span>✨ 捏造新声线角色</span>
          <Icon name="arrow-right" size="sm" />
        </button>
      </div>
    </div>

    <div class="clone-workbench">
      <!-- 左侧：发音角色资产库（310px，与 DesignTab 预设库完全对称） -->
      <aside class="personas-sidebar">
        <div class="sidebar-header">
          <div class="section-title">
            <Icon name="voice" size="sm" />
            <span>🎙️ 我的声音资产</span>
          </div>
          <span class="persona-badge">{{ personasArr.length }} 位</span>
        </div>

        <div class="persona-search-box">
          <Icon name="search" size="sm" class="search-icon" />
          <input
            v-model="personaSearch"
            type="text"
            placeholder="搜索发音角色、描述..."
            class="persona-search-input"
          />
          <button v-if="personaSearch" class="clear-search-btn" @click="personaSearch = ''" title="清除">
            <Icon name="close" size="sm" />
          </button>
        </div>

        <div class="personas-scroll-list scroll-y">
          <div
            v-for="p in filteredPersonas"
            :key="p.key"
            class="persona-card"
            :class="{ active: selectedPersona === p.key }"
            tabindex="0"
            @click="selectPersona(p.key)"
            @keydown.enter.prevent="selectPersona(p.key)"
          >
            <div class="persona-card-head">
              <div class="persona-avatar">
                {{ (p.name || p.key).charAt(0).toUpperCase() }}
              </div>
              <div class="persona-name-col">
                <div class="persona-name-row">
                  <span class="persona-name" :title="p.name || p.key">{{ p.name || p.key }}</span>
                  <span v-if="selectedPersona === p.key" class="using-badge">配音中</span>
                </div>
                <span class="persona-status-tag" :class="p.has_audio ? 'ready' : 'empty'">
                  {{ p.has_audio ? '✓ 样音就绪' : '待配置' }}
                </span>
              </div>
              <button
                v-if="p.has_audio"
                class="persona-play-btn"
                :class="{ playing: previewKey === p.key }"
                :title="previewKey === p.key ? '暂停试听' : '试听样音'"
                @click.stop="togglePreview(p.key)"
              >
                <Icon :name="previewKey === p.key ? 'pause' : 'play'" size="sm" />
              </button>
            </div>
            <div class="persona-desc" :title="p.desc || p.instruction">
              {{ p.desc || p.instruction || '已装载声音特征' }}
            </div>
          </div>
          <div v-if="filteredPersonas.length === 0" class="persona-empty">
            <p v-if="personaSearch">未找到「{{ personaSearch }}」相关角色</p>
            <p v-else>暂无发音角色</p>
          </div>
        </div>

        <button class="new-persona-btn" @click="goToDesign">
          <Icon name="plus" size="sm" />
          <span>✨ 捏造/录制新声线</span>
        </button>
      </aside>

      <!-- 右侧：核心配音输入工作区 -->
      <section class="studio">
        <!-- 顶栏状态与快捷工具栏 -->
        <div class="studio-header-bar">
          <div class="speaker-indicator" :class="{ 'warning-indicator': !selectedPersona }">
            <Icon name="voice" size="sm" />
            <span v-if="selectedPersona">当前发音人：<strong>{{ currentPersonaName }}</strong></span>
            <span v-else class="warn-text">⚠️ 请在左侧选择发音角色</span>
          </div>

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
            :rows="6"
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
            <n-button @click="saveScript">
              <Icon name="save" size="sm" />
              <span>保存为草稿</span>
            </n-button>
          </div>
          <n-button type="primary" class="glow"
            :disabled="!selectedPersona || !cloneForm.text.trim()"
            @click="handleSynthesize"
          >
            <Icon name="play" size="sm" />
            <span>立即合成音频</span>
          </n-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted, ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import AIHelpSection from '../components/AIHelpSection.vue';
import ModelSetupCard from '../components/ModelSetupCard.vue';
import Icon from '../components/Icon.vue';

import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const router = useRouter();
const capabilitiesStore = useCapabilitiesStore();
const synthStore = useSynthStore();
const tasksStore = useTasksStore();
const voicesStore = useVoicesStore();

const { modelStatus } = storeToRefs(capabilitiesStore);
const { selectedPersona, personas, previewKey } = storeToRefs(voicesStore);
const { selectPersona, togglePreview } = voicesStore;
const { savedScripts } = storeToRefs(synthStore);

const personaSearch = ref('');

const personasArr = computed(() =>
  Object.entries(personas.value || {}).map(([key, p]) => ({ key, ...p })),
);

const filteredPersonas = computed(() => {
  const kw = personaSearch.value.trim().toLowerCase();
  if (!kw) return personasArr.value;
  return personasArr.value.filter(
    (p) => (p.name || '').toLowerCase().includes(kw)
      || p.key.toLowerCase().includes(kw)
      || (p.desc || '').toLowerCase().includes(kw)
      || (p.instruction || '').toLowerCase().includes(kw),
  );
});

const currentPersonaName = computed(() => {
  if (!selectedPersona.value) return '';
  const p = personas.value?.[selectedPersona.value];
  return p?.name || selectedPersona.value;
});

const goToDesign = () => {
  router.push({ name: 'design' });
};

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
  if (!selectedPersona.value) return tasksStore.showToast('请先选择发音角色', 'warning');
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
  } catch {
    // 错误已进日志
  }
};

const loadScript = (script) => {
  synthStore.loadScript(script);
  showDrafts.value = false;
  tasksStore.showToast('已载入草稿内容', 'info');
};

const deleteScript = (id) => synthStore.deleteScript(id);

onMounted(() => synthStore.loadScripts());
</script>

<style scoped>
.tab-content-container {
  max-width: 1180px;
  margin: 0 auto;
}

/* 顶层指引横幅 */
.clone-flow-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  margin-bottom: var(--vf-space-4);
}
.banner-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.banner-text-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.banner-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-primary);
}
.banner-desc {
  font-size: 12px;
  color: var(--vf-text-3);
  line-height: 1.4;
}
.goto-design-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-full);
  color: var(--vf-text-1);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s var(--vf-ease);
  white-space: nowrap;
}
.goto-design-btn:hover {
  background: var(--vf-bg-hover);
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  transform: translateX(2px);
}

/* 左右分栏工作台：严格 310px + 1fr 对齐 DesignTab */
.clone-workbench {
  display: grid;
  grid-template-columns: 310px 1fr;
  gap: var(--vf-space-4);
  align-items: start;
}

/* 左侧：发音角色资产库 */
.personas-sidebar {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
  height: 560px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--vf-space-2);
  border-bottom: 1px solid var(--vf-border);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.persona-badge {
  font-size: 11px;
  color: var(--vf-text-3);
  background: var(--vf-bg-3);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}

.persona-search-box {
  position: relative;
  display: flex;
  align-items: center;
}
.persona-search-box .search-icon {
  position: absolute;
  left: 8px;
  color: var(--vf-text-3);
  pointer-events: none;
}
.persona-search-input {
  width: 100%;
  padding: 6px 26px 6px 28px;
  background: var(--vf-bg-1);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-1);
  font-size: 12px;
  outline: none;
  transition: border-color 0.2s;
}
.persona-search-input:focus {
  border-color: var(--vf-primary);
}
.clear-search-btn {
  position: absolute;
  right: 6px;
  background: none;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
}
.clear-search-btn:hover {
  color: var(--vf-text-1);
}

.personas-scroll-list {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-2);
  flex: 1;
  padding-right: 4px;
}

.persona-card {
  padding: var(--vf-space-3);
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: all 0.15s var(--vf-ease);
  outline: none;
}
.persona-card:hover,
.persona-card:focus-visible {
  border-color: var(--vf-border-strong);
  background: var(--vf-bg-hover);
  transform: translateY(-1px);
}
.persona-card.active {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
}

.persona-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.persona-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--vf-bg-4);
  color: var(--vf-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.persona-name-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.persona-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.persona-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.using-badge {
  font-size: 10px;
  color: var(--vf-primary);
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid var(--vf-primary);
  padding: 0 5px;
  border-radius: var(--vf-radius-full);
  white-space: nowrap;
}
.persona-status-tag {
  font-size: 10px;
}
.persona-status-tag.ready {
  color: var(--vf-primary);
}
.persona-status-tag.empty {
  color: var(--vf-text-3);
}
.persona-play-btn {
  background: var(--vf-bg-4);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.persona-play-btn:hover {
  background: var(--vf-primary);
  color: white;
  border-color: var(--vf-primary);
}
.persona-play-btn.playing {
  background: var(--vf-primary);
  color: white;
  border-color: var(--vf-primary);
  animation: pulse 1.5s infinite;
}
.persona-desc {
  font-size: 11px;
  color: var(--vf-text-3);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.persona-empty {
  padding: 30px 0;
  text-align: center;
  font-size: 12px;
  color: var(--vf-text-3);
}

.new-persona-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 8px;
  background: var(--vf-bg-3);
  border: 1px dashed var(--vf-border-strong);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-2);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.new-persona-btn:hover {
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
}

/* 右侧核心工作台 */
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
.studio-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--vf-space-3);
  border-bottom: 1px solid var(--vf-border);
  gap: 12px;
}

.speaker-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--vf-text-1);
  background: var(--vf-bg-3);
  padding: 4px 10px;
  border-radius: var(--vf-radius-full);
  border: 1px solid var(--vf-border);
}
.speaker-indicator strong {
  color: var(--vf-primary);
}
.speaker-indicator.warning-indicator {
  background: rgba(234, 179, 8, 0.1);
  border-color: rgba(234, 179, 8, 0.3);
}
.warn-text {
  color: #f59e0b;
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



@media (max-width: 860px) {
  .clone-workbench {
    grid-template-columns: 1fr;
  }
  .personas-sidebar {
    height: 260px;
  }
  .params-grid {
    grid-template-columns: 1fr;
  }
}
</style>
