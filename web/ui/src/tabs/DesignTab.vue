<template>
  <div class="tab-content-container">
    <!-- 模型未就绪卡片 -->
    <ModelSetupCard v-if="!modelStatus.design.ready" model="VoiceDesign" />

    <header class="page-head">
      <div>
        <h2 class="page-title">音色设计</h2>
        <p class="page-sub">用文字描述一个声音，本机生成样音。模板只生成一次，生成后加入「我的声音」即可配音。</p>
      </div>
      <div class="page-actions">
        <button class="ghost-btn" @click="router.push({ name: 'library' })">生成库</button>
        <button class="ghost-btn" @click="goToAssets">我的声音 · {{ personasCount }}</button>
      </div>
    </header>

    <div class="design-workbench">
      <!-- 左侧：官方灵感预设库（Prompt 模板，点击即自动填入右侧表单） -->
      <aside v-if="designPresets.length > 0" class="presets-sidebar">
        <div class="sidebar-header">
          <div class="section-title">
            <span>设计模板</span>
          </div>
          <div class="preset-filter" role="tablist">
            <button :aria-pressed="presetView === 'pending'" @click="presetView = 'pending'">待生成 {{ pendingCount }}</button>
            <button :aria-pressed="presetView === 'all'" @click="presetView = 'all'">全部 {{ designPresets.length }}</button>
          </div>
        </div>

        <div class="preset-search-box">
          <Icon name="search" size="sm" class="search-icon" />
          <input
            v-model="presetSearch"
            type="text"
            placeholder="搜索预设风格、语气描述..."
            class="preset-search-input"
          />
          <button v-if="presetSearch" class="clear-search-btn" @click="presetSearch = ''" title="清除">
            <Icon name="close" size="sm" />
          </button>
        </div>

        <div class="presets-scroll-list scroll-y">
          <div
            v-for="(p, idx) in filteredPresets"
            :key="idx"
            class="preset-item"
            :class="{ active: selectedPresetName === p.voice_name }"
            tabindex="0"
            @click="applyPreset(p)"
            @keydown.enter.prevent="applyPreset(p)"
          >
            <div class="preset-item-head">
              <span class="preset-name">{{ p.voice_name }}</span>
              <span v-if="p.has_generated" class="using-badge">已生成</span>
              <span v-else-if="selectedPresetName === p.voice_name" class="using-badge">已套用</span>
            </div>
            <div class="preset-tone">{{ p.tone }}</div>
            <div class="preset-text" :title="p.text">{{ p.text }}</div>
            <button v-if="p.audio_url" class="preset-play" :aria-label="`试听 ${p.voice_name}`"
              @click.stop="library.playAudio(p.audio_url, p.voice_name)">
              <Icon name="play" size="xs" /> 试听样音
            </button>
          </div>
          <div v-if="filteredPresets.length === 0" class="preset-empty">
            <template v-if="presetSearch">没有匹配「{{ presetSearch }}」的模板</template>
            <template v-else-if="presetView === 'pending'">模板都生成过了，切到「全部」可以试听</template>
          </div>
        </div>
      </aside>

      <!-- 右侧：核心音色创作工作台 -->
      <main class="design-editor-pane">
        <section class="form-card">
          <div class="form-card-head">
            <div class="pane-title">
              <Icon name="design" size="sm" />
              <span>描述一个新声音</span>
            </div>
            <div v-if="selectedPresetName" class="using-preset-tag">
              <span>已套用预设: {{ selectedPresetName }}</span>
              <button class="clear-preset-btn" title="清除并清空表单" @click="clearPreset">✕</button>
            </div>
          </div>

          <div class="grid-2">
            <div class="form-cell">
              <label class="form-label"><Icon name="voice" size="sm" />新音色名称</label>
              <n-input
                v-model:value="designForm.name"
                placeholder="如：冷酷刺客 / 温柔主播"
              />
            </div>
            <div class="form-cell">
              <label class="form-label"><Icon name="speech" size="sm" />语气描述</label>
              <n-input
                v-model:value="designForm.tone"
                placeholder="如：声音低沉、沙哑、冰冷，语速缓慢"
              />
            </div>
          </div>

          <div class="form-cell">
            <div class="label-row">
              <label class="form-label"><Icon name="edit" size="sm" />建模配音短句（声音母本，15-50 字）</label>
              <span class="text-counter">{{ (designForm.text || '').length }} 字</span>
            </div>
            <n-input
              v-model:value="designForm.text"
              type="textarea"
              :rows="4"
              placeholder="如：风啸声起，剑影重重，这十年来，我从未有一刻忘记过这一剑的承诺。"
            />
          </div>

          <div class="form-cell">
            <label class="form-label"><Icon name="mask" size="sm" />情绪控制描述</label>
            <n-input
              v-model:value="designForm.emotion"
              placeholder="如：非常开心、咬牙切齿、悲伤抽泣（不填默认使用基础声音）"
            />
          </div>

          <div class="form-footer">
            <label class="commit-row">
              <n-switch v-model:value="designForm.commit" />
              <span>生成后直接加入「我的声音」</span>
              <span class="commit-tip">关闭时结果只进入生成库，试听满意后再到生成库点「加入我的声音」</span>
            </label>
            <n-button type="primary" class="glow"
              :disabled="!designForm.name.trim() || !designForm.text.trim() || !modelStatus.design.ready || selectedPresetGenerated"
              @click="doDesign(selectedPresetName)"
            >
              <Icon name="design" size="sm" />
              <span>{{ selectedPresetGenerated ? '模板已生成，请到生成库查看' : '合成并设计音色' }}</span>
            </n-button>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useVoicesStore } from '../stores/voices';
import { useTasksStore } from '../stores/tasks';
import { useLibraryStore } from '../stores/library';
import ModelSetupCard from '../components/ModelSetupCard.vue';
import Icon from '../components/Icon.vue';

const router = useRouter();
const library = useLibraryStore();
const synthStore = useSynthStore();
const { designPresets } = storeToRefs(synthStore);
const { designForm, doDesign } = synthStore;
const capabilitiesStore = useCapabilitiesStore();
const { modelStatus } = storeToRefs(capabilitiesStore);
const voicesStore = useVoicesStore();
const { personas } = storeToRefs(voicesStore);
const { showToast } = useTasksStore();

const selectedPresetName = ref('');
const presetSearch = ref('');

const personasCount = computed(() => Object.values(personas.value || {})
  .filter((p) => p?.favorite !== false).length);
const selectedPresetGenerated = computed(() => designPresets.value.some(
  (p) => p.voice_name === selectedPresetName.value && p.has_generated,
));

// 模板只生成一次：默认只列还没生成的，生成过的切到「全部」能看到并试听。
const presetView = ref('pending');
const pendingCount = computed(() => designPresets.value.filter((p) => !p.has_generated).length);
const filteredPresets = computed(() => {
  const kw = presetSearch.value.trim().toLowerCase();
  const base = presetView.value === 'pending'
    ? designPresets.value.filter((p) => !p.has_generated)
    : designPresets.value;
  if (!kw) return base;
  return base.filter(
    (p) => (p.voice_name || '').toLowerCase().includes(kw)
      || (p.tone || '').toLowerCase().includes(kw)
      || (p.text || '').toLowerCase().includes(kw),
  );
});

const applyPreset = (preset) => {
  selectedPresetName.value = preset.voice_name || '';
  designForm.name = preset.voice_name || '';
  designForm.tone = preset.tone || '';
  designForm.text = preset.text || '';
  designForm.emotion = preset.emotion || '';
  showToast(`已套用预设: ${preset.voice_name}`, 'success');
};

const clearPreset = () => {
  selectedPresetName.value = '';
  designForm.name = '';
  designForm.tone = '';
  designForm.text = '';
  designForm.emotion = '';
};

const goToAssets = () => {
  router.push({ name: 'clone' });
};
</script>

<style scoped>
/* 左右分栏工作台 */
.design-workbench {
  display: grid;
  grid-template-columns: 310px 1fr;
  gap: var(--vf-space-4);
  align-items: start;
}

/* 左侧预设库 */
.presets-sidebar {
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

.preset-filter { display: inline-flex; gap: 2px; padding: 2px; background: var(--vf-bg-1); border: 1px solid var(--vf-border); border-radius: var(--vf-radius-full); }
.preset-filter button { padding: 3px 10px; font-size: 12px; color: var(--vf-text-3); background: transparent; border: 0; border-radius: var(--vf-radius-full); cursor: pointer; }
.preset-filter button[aria-pressed="true"] { color: var(--vf-text-1); background: var(--vf-bg-3); }

.preset-search-box {
  position: relative;
  display: flex;
  align-items: center;
}
.preset-search-box .search-icon {
  position: absolute;
  left: 8px;
  color: var(--vf-text-3);
  pointer-events: none;
}
.preset-search-input {
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
.preset-search-input:focus {
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
.preset-empty {
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  color: var(--vf-text-3);
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

.preset-badge {
  font-size: var(--vf-fs-xs);
  color: var(--vf-text-3);
  background: var(--vf-bg-3);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}

.presets-scroll-list {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-2);
  flex: 1;
  padding-right: 4px;
}

.preset-item {
  padding: var(--vf-space-3);
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: all 0.15s var(--vf-ease);
  outline: none;
}

.preset-item:hover,
.preset-item:focus-visible {
  border-color: var(--vf-border-strong);
  background: var(--vf-bg-hover);
  transform: translateY(-1px);
}

.preset-item.active {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
}

.preset-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preset-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.using-badge {
  font-size: var(--vf-fs-xs);
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
  padding: 1px 6px;
  border-radius: var(--vf-radius-full);
}

.preset-tone {
  font-size: var(--vf-fs-xs);
  color: var(--vf-text-2);
  line-height: 1.4;
}

.preset-play {
  display: inline-flex;
  align-items: center;
  gap: var(--vf-space-1);
  margin-top: var(--vf-space-2);
  padding: var(--vf-space-1) var(--vf-space-3);
  background: var(--vf-primary-soft);
  border: 1px solid transparent;
  border-radius: var(--vf-radius-full);
  color: var(--vf-primary-hover);
  font-size: 12px;
  cursor: pointer;
}
.preset-play:hover { border-color: var(--vf-primary); }
.preset-play:focus-visible { outline: 2px solid var(--vf-primary); outline-offset: 2px; }
.preset-text {
  font-size: var(--vf-fs-xs);
  color: var(--vf-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 右侧表单主区 */
.design-editor-pane {
  display: flex;
  flex-direction: column;
}

.form-card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}

.form-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--vf-space-3);
  border-bottom: 1px solid var(--vf-border);
}

.pane-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.using-preset-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--vf-fs-xs);
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
}
.clear-preset-btn {
  background: none;
  border: none;
  color: var(--vf-primary);
  cursor: pointer;
  padding: 0 2px;
  font-size: var(--vf-fs-xs);
  opacity: 0.7;
}
.clear-preset-btn:hover {
  opacity: 1;
}

.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vf-space-4);
}

.form-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.label-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.text-counter {
  font-size: var(--vf-fs-xs);
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
}

.form-label {
  font-size: 12px;
  color: var(--vf-text-2);
}

.form-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: var(--vf-space-4);
  border-top: 1px solid var(--vf-border);
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}

.commit-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  color: var(--vf-text-1);
  cursor: pointer;
  flex-wrap: wrap;
}

.commit-tip {
  font-size: var(--vf-fs-xs);
  color: var(--vf-text-3);
}

@media (max-width: 860px) {
  .design-workbench {
    grid-template-columns: 1fr;
  }
  .presets-sidebar {
    height: 240px;
  }
  .grid-2 {
    grid-template-columns: 1fr;
  }
}
</style>
