<template>
  <div class="tab-content-container">
    <!-- 模型未就绪卡片 -->
    <ModelSetupCard v-if="!modelStatus.design.ready" model="VoiceDesign" />

    <div class="design-workbench">
      <!-- 左侧：声音配方库（紧凑可滚动选择栏） -->
      <aside v-if="designPresets.length > 0" class="presets-sidebar">
        <div class="sidebar-header">
          <div class="section-title">
            <Icon name="sparkles" size="sm" />
            <span>预设配方库</span>
          </div>
          <span class="preset-badge">{{ designPresets.length }} 款</span>
        </div>

        <div class="presets-scroll-list scroll-y">
          <div
            v-for="(p, idx) in designPresets"
            :key="idx"
            class="preset-item"
            :class="{ active: selectedPresetName === p.voice_name }"
            tabindex="0"
            @click="applyPreset(p)"
            @keydown.enter.prevent="applyPreset(p)"
          >
            <div class="preset-item-head">
              <span class="preset-name">{{ p.voice_name }}</span>
              <span v-if="selectedPresetName === p.voice_name" class="active-dot" />
            </div>
            <div class="preset-tone">{{ p.tone }}</div>
            <div class="preset-text" :title="p.text">{{ p.text }}</div>
          </div>
        </div>
      </aside>

      <!-- 右侧：核心音色创作工作台 -->
      <main class="design-editor-pane">
        <section class="form-card">
          <div class="form-card-head">
            <div class="pane-title">
              <Icon name="design" size="sm" />
              <span>音色参数配置</span>
            </div>
            <span v-if="selectedPresetName" class="using-preset-tag">
              已套用: {{ selectedPresetName }}
            </span>
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
              <span class="commit-tip">合成完成自动入库并带上 ✓ 样音标识</span>
            </label>
            <button
              class="primary-btn"
              :disabled="!designForm.name.trim() || !designForm.text.trim() || !modelStatus.design.ready"
              @click="doDesign"
            >
              <Icon name="design" size="sm" />
              <span>合成并设计音色</span>
            </button>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import ModelSetupCard from '../components/ModelSetupCard.vue';
import Icon from '../components/Icon.vue';

const synthStore = useSynthStore();
const { designPresets } = storeToRefs(synthStore);
const { designForm, doDesign } = synthStore;
const capabilitiesStore = useCapabilitiesStore();
const { modelStatus } = storeToRefs(capabilitiesStore);
const { showToast } = useTasksStore();

const selectedPresetName = ref('');

const applyPreset = (preset) => {
  selectedPresetName.value = preset.voice_name || '';
  designForm.name = preset.voice_name || '';
  designForm.tone = preset.tone || '';
  designForm.text = preset.text || '';
  designForm.emotion = preset.emotion || '';
  showToast(`已套用预设: ${preset.voice_name}`, 'success');
};
</script>

<style scoped>
.tab-content-container {
  max-width: 1180px;
  margin: 0 auto;
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
  height: 520px;
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

.active-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--vf-primary);
  box-shadow: 0 0 6px var(--vf-primary);
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
  font-size: 11px;
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
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
