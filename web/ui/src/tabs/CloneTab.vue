<template>
  <div class="tab-content-container">
    <!-- 模型未就绪 / 正在下载 -->
    <ModelSetupCard v-if="!modelStatus.base.ready" model="Base" />

    <header class="page-head">
      <div>
        <h2 class="page-title">我的声音</h2>
        <p class="page-sub">录 10–20 秒自己的声音并填上原文，就能克隆。选中一个声音，输入文字生成配音。</p>
      </div>
      <div class="page-actions">
        <button class="ghost-btn" @click="goToDesign">设计新音色</button>
        <button class="primary-btn" @click="$emit('add-persona')">
          <Icon name="plus" size="sm" /> 录制 / 导入我的声音
        </button>
      </div>
    </header>

    <!-- 一个声音都没有时：工作台没有意义，给三步引导，不让人对着空的配音框发呆 -->
    <section v-if="personasArr.length === 0" class="first-run">
      <h3>先有一个声音，才能配音</h3>
      <ol class="first-run-steps">
        <li><strong>录 15 秒</strong><span>照着屏幕上的一段话念，安静环境就行</span></li>
        <li><strong>起个名字</strong><span>保存后它就在「我的声音」里</span></li>
        <li><strong>输入文字配音</strong><span>选中声音，写字，点生成</span></li>
      </ol>
      <div class="first-run-actions">
        <button class="primary-btn" @click="$emit('add-persona')"><Icon name="voice" size="sm" /> 录制我的声音</button>
        <button class="ghost-btn" @click="goToDesign">没有麦克风？用文字设计一个</button>
      </div>
    </section>

    <div v-else class="clone-workbench">
      <!-- 左侧：发音角色资产库（310px，与 DesignTab 预设库完全对称） -->
      <aside class="personas-sidebar">
        <div class="sidebar-header">
          <div class="section-title">
            <span>我的声音</span>
            <span class="persona-badge">{{ personasArr.filter(p => p.favorite !== false).length }}</span>
          </div>
          <button class="voice-filter" :aria-pressed="showAllVoices" @click="showAllVoices = !showAllVoices">
            {{ showAllVoices ? '只看我的声音' : '显示已移出的' }}
          </button>
        </div>
        <div class="persona-search-box">
          <Icon name="search" size="sm" class="search-icon" />
          <input
            v-model="personaSearch"
            type="text"
            placeholder="搜索声音"
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
            <div v-if="p.desc || p.instruction" class="persona-desc" :title="p.desc || p.instruction">
              {{ p.desc || p.instruction }}
            </div>
            <div class="voice-actions" @click.stop>
              <button @click="toggleFavorite(p)">{{ p.favorite === false ? '加入我的声音' : '移出我的声音' }}</button>
              <button @click="startRename(p)">重命名</button>
              <button v-if="p.favorite === false" class="danger" @click="removeVoice(p)">删除</button>
            </div>
          </div>
          <div v-if="filteredPersonas.length === 0" class="persona-empty">
            <p v-if="personaSearch">没有叫「{{ personaSearch }}」的声音</p>
            <template v-else>
              <p>还没有声音</p>
              <button class="primary-btn small" @click="$emit('add-persona')">录制我的声音</button>
            </template>
          </div>
        </div>

      </aside>

      <!-- 右侧：核心配音输入工作区 -->
      <section class="studio">
        <!-- 顶栏状态与快捷工具栏 -->
        <div class="studio-header-bar">
          <div class="speaker-indicator" :class="{ 'warning-indicator': !selectedPersona }">
            <Icon name="voice" size="sm" />
            <span v-if="selectedPersona">当前发音人：<strong>{{ currentPersonaName }}</strong></span>
            <span v-else class="warn-text">先在左侧选一个声音</span>
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

        <!-- 克隆声音只学音色：MLX base 没有情绪指令入口（core/modes/cloner.py）。
             以前这里摆着「快捷语气 / 情绪标签 / 情绪优先」，点了没有任何效果 —— 删掉，说实话。 -->
        <p class="emotion-hint">
          <Icon name="info" size="sm" />
          克隆的声音会照着样音的语气说话。想要更激动或更温柔，直接写进文字里（标点、语气词都有用），或换一段同样语气的样音重新录。
        </p>

        <!-- 底部控制栏 -->
        <div class="studio-footer">
          <div class="footer-left">
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
    <n-modal v-model:show="renameDialog" preset="card" title="重命名音色" style="width: min(420px, 92vw)">
      <n-input v-model:value="renameValue" placeholder="输入新的显示名称" @keydown.enter="saveRename" />
      <template #footer><n-button type="primary" @click="saveRename">保存</n-button></template>
    </n-modal>
  </div>
</template>

<script setup>
defineEmits(['add-persona']);
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
const showAllVoices = ref(false);
const renameDialog = ref(false);
const renameValue = ref('');
const renameKey = ref('');
const toggleFavorite = async (p) => {
  try {
    await voicesStore.updatePersona(p.key, { favorite: p.favorite === false });
  } catch (error) { tasksStore.showToast(`操作失败：${error.message || error}`, 'error'); }
};
const startRename = (p) => { renameKey.value = p.key; renameValue.value = p.name || p.key; renameDialog.value = true; };
const saveRename = async () => {
  if (!renameValue.value.trim()) return tasksStore.showToast('请填写音色名称', 'error');
  try {
    await voicesStore.updatePersona(renameKey.value, { name: renameValue.value.trim() });
    renameDialog.value = false;
    tasksStore.showToast('音色已重命名', 'success');
  } catch (error) { tasksStore.showToast(`重命名失败：${error.message || error}`, 'error'); }
};
const removeVoice = async (p) => {
  const name = p.name || p.key;
  // 规则与生成库、CLI 一致：在「我的声音」里的不能删，先移出再删。
  if (p.favorite !== false) {
    return tasksStore.showToast('先「移出我的声音」，才能删除', 'warning');
  }
  if (!window.confirm(`删除声音「${name}」？\n\n· 它会从列表里消失，配音时不能再选\n· 原始录音文件保留在本机，不会被删\n· 这一步不能撤销`)) return;
  try { await voicesStore.deletePersona(p.key, true); }
  catch (error) { tasksStore.showToast(`删除失败：${error.message || error}`, 'error'); }
};

const personasArr = computed(() =>
  Object.entries(personas.value || {}).map(([key, p]) => ({ key, ...p })),
);

const filteredPersonas = computed(() => {
  const kw = personaSearch.value.trim().toLowerCase();
  return personasArr.value.filter((p) => (showAllVoices.value || p.favorite !== false) &&
    (!kw || (p.name || '').toLowerCase().includes(kw)
      || p.key.toLowerCase().includes(kw)
      || (p.desc || '').toLowerCase().includes(kw)
      || (p.instruction || '').toLowerCase().includes(kw)));

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
});

const handleSynthesize = () => {
  if (!selectedPersona.value) return tasksStore.showToast('请先选择发音角色', 'warning');
  if (!cloneForm.text.trim()) return tasksStore.showToast('请输入合成文案', 'warning');
  synthStore.doClone({
    mode: 'clone',
    persona: selectedPersona.value,
    text: cloneForm.text,
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
.voice-filter, .voice-actions button {
  color: var(--vf-text-2);
  background: transparent;
  border: 1px solid var(--vf-border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  padding: 5px 8px;
}
.voice-filter { padding: 3px 8px; }
.voice-filter[aria-pressed="true"] { color: var(--vf-primary-hover); border-color: var(--vf-primary); }
/* 操作只在选中 / 悬停 / 键盘聚焦时出现：列表扫读时只看名字，不被一排按钮淹没。 */
.voice-actions { display: none; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.persona-card.active .voice-actions,
.persona-card:hover .voice-actions,
.persona-card:focus-within .voice-actions { display: flex; }
.voice-actions button:hover, .voice-filter:hover { color: var(--vf-text-1); }
/* 左右分栏工作台：严格 310px + 1fr 对齐 DesignTab */
.first-run {
  margin-top: var(--vf-space-6);
  padding: var(--vf-space-8, 32px) var(--vf-space-6);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  text-align: center;
}
.first-run h3 { margin: 0 0 var(--vf-space-4); font-size: 16px; font-weight: 600; color: var(--vf-text-1); }
.first-run-steps {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--vf-space-3);
  max-width: 720px; margin: 0 auto var(--vf-space-6); padding: 0; list-style: none; counter-reset: step;
}
.first-run-steps li {
  counter-increment: step; display: flex; flex-direction: column; gap: 4px;
  padding: var(--vf-space-3); background: var(--vf-bg-1); border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm); font-size: 12px; color: var(--vf-text-2);
}
.first-run-steps li::before { content: counter(step); font-size: 18px; font-weight: 700; color: var(--vf-primary); }
.first-run-steps strong { font-size: 13px; color: var(--vf-text-1); }
.first-run-actions { display: flex; justify-content: center; gap: var(--vf-space-2); flex-wrap: wrap; }
@media (max-width: 640px) { .first-run-steps { grid-template-columns: 1fr; } }

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
  /* 跟着窗口高度走：小屏不溢出、大屏不留半屏空白（原来写死 560px） */
  height: clamp(420px, calc(100vh - var(--vf-header-h) - var(--vf-player-h) - 190px), 820px);
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
  font-size: var(--vf-fs-xs);
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
  font-size: var(--vf-fs-xs);
  color: var(--vf-primary);
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid var(--vf-primary);
  padding: 0 5px;
  border-radius: var(--vf-radius-full);
  white-space: nowrap;
}
.persona-status-tag {
  font-size: var(--vf-fs-xs);
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
  font-size: var(--vf-fs-xs);
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
  font-size: var(--vf-fs-xs);
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

/* 语气说明：克隆不支持情绪指令，如实告知 */
.emotion-hint {
  display: flex;
  align-items: flex-start;
  gap: var(--vf-space-2);
  margin: 0;
  padding: var(--vf-space-2) var(--vf-space-3);
  font-size: 12px;
  line-height: 1.6;
  color: var(--vf-text-2);
  background: var(--vf-bg-1);
  border: 1px dashed var(--vf-border);
  border-radius: var(--vf-radius-sm);
}
.voice-actions button.danger:hover { color: var(--vf-err); border-color: var(--vf-err); }

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

@media (max-width: 860px) {
  .clone-workbench {
    grid-template-columns: 1fr;
  }
  .personas-sidebar {
    height: 260px;
  }
}
</style>
