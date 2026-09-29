<template>
  <div class="tab-content-container">
    <!-- 模型未就绪卡片 -->
    <ModelSetupCard v-if="!modelStatus.design.ready" model="VoiceDesign" />

    <!-- 顶层流程指引 -->
    <div class="design-flow-banner">
      <div class="banner-left">
        <Icon name="sparkles" size="sm" />
        <div class="banner-text-group">
          <span class="banner-title">声音工坊 · 音色设计：凭空塑造独一无二的 AI 专属声线</span>
          <span class="banner-desc">
            从左侧「官方灵感预设」挑选模板或自由填写；合成入库后将沉淀至「我的声音资产」，供【文本配音】与【Suno 歌手】调用！
          </span>
        </div>
      </div>
      <div class="banner-right">
        <button class="goto-assets-btn" @click="goToAssets">
          <Icon name="voice" size="sm" />
          <span>查看我的声音资产 ({{ personasCount }})</span>
          <Icon name="arrow-right" size="sm" />
        </button>
      </div>
    </div>

    <div class="design-workbench">
      <!-- 左侧：官方灵感预设库（Prompt 模板，点击即自动填入右侧表单） -->
      <aside v-if="designPresets.length > 0" class="presets-sidebar">
        <div class="sidebar-header">
          <div class="section-title">
            <Icon name="sparkles" size="sm" />
            <span>✨ 官方灵感预设</span>
          </div>
          <span class="preset-badge">{{ filteredPresets.length }} 款模板</span>
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
              <span v-if="selectedPresetName === p.voice_name" class="using-badge">已套用</span>
            </div>
            <div class="preset-tone">{{ p.tone }}</div>
            <div class="preset-text" :title="p.text">{{ p.text }}</div>
          </div>
          <div v-if="filteredPresets.length === 0" class="preset-empty">
            没有匹配「{{ presetSearch }}」的灵感模板
          </div>
        </div>
      </aside>

      <!-- 右侧：核心音色创作工作台 -->
      <main class="design-editor-pane">
        <section class="form-card">
          <div class="form-card-head">
            <div class="pane-title">
              <Icon name="design" size="sm" />
              <span>凭空捏造新声线</span>
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
              <span>满意后存入标准样音库</span>
              <span class="commit-tip">合成完成自动沉淀为【我的声音资产】并带上 ✓ 样音标识</span>
            </label>
            <n-button type="primary" class="glow"
              :disabled="!designForm.name.trim() || !designForm.text.trim() || !modelStatus.design.ready"
              @click="doDesign"
            >
              <Icon name="design" size="sm" />
              <span>合成并设计音色</span>
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
import ModelSetupCard from '../components/ModelSetupCard.vue';
import Icon from '../components/Icon.vue';

const router = useRouter();
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

const personasCount = computed(() => Object.keys(personas.value || {}).length);

const filteredPresets = computed(() => {
  const kw = presetSearch.value.trim().toLowerCase();
  if (!kw) return designPresets.value;
  return designPresets.value.filter(
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
.tab-content-container {
  max-width: 1180px;
  margin: 0 auto;
}

/* 顶层指引横幅 */
.design-flow-banner {
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

.goto-assets-btn {
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
.goto-assets-btn:hover {
  background: var(--vf-bg-hover);
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  transform: translateX(2px);
}

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
  height: 560px;
}

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
  font-size: 11px;
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
  font-size: 10px;
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
  padding: 1px 6px;
  border-radius: var(--vf-radius-full);
}

.preset-tone {
  font-size: 11px;
  color: var(--vf-text-2);
  line-height: 1.4;
}

.preset-text {
  font-size: 11px;
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
  font-size: 11px;
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
  font-size: 11px;
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
  font-size: 11px;
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
  font-size: 11px;
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
