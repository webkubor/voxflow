<template>
  <div class="tab-content-container">
    <WarnBanner
      v-if="!modelStatus.design.ready && !modelStatus.design.downloading"
      type="warn"
      title="VoiceDesign 设计大模型未下载"
      hint="请在终端先跑 ./install.sh（选择下载音色设计大模型），否则音色设计功能无法运行。"
    />

    <WarnBanner
      v-else-if="modelStatus.design.downloading"
      type="info"
      title="VoiceDesign 模型正在下载"
    >
      <n-progress
        type="line"
        :percentage="modelStatus.design.progress || 0"
        :show-indicator="true"
      />
    </WarnBanner>

    <!-- 预设配方 -->
    <section v-if="designPresets.length > 0" class="presets-section">
      <div class="section-title">
        <Icon name="sparkles" size="sm" />
        <span>一键套用预设声音配方</span>
      </div>
      <div class="presets-grid">
        <div
          v-for="(p, idx) in designPresets"
          :key="idx"
          class="preset-card"
          tabindex="0"
          @click="applyPreset(p)"
          @keydown.enter.prevent="applyPreset(p)"
        >
          <div class="preset-head">
            <span class="preset-name">{{ p.voice_name }}</span>
            <Icon name="arrow-right" size="sm" />
          </div>
          <div class="preset-tone">{{ p.tone }}</div>
          <div class="preset-text" :title="p.text">短句: {{ p.text }}</div>
        </div>
      </div>
    </section>

    <!-- 表单 -->
    <section class="form-card">
      <div class="grid-2">
        <div class="form-cell">
          <label class="form-label">🎙️ 新音色名称</label>
          <n-input
            v-model:value="designForm.name"
            placeholder="如：冷酷刺客 / 温柔主播"
          />
        </div>
        <div class="form-cell">
          <label class="form-label">🗣️ 语气描述</label>
          <n-input
            v-model:value="designForm.tone"
            placeholder="如：声音低沉、沙哑、冰冷，语速缓慢"
          />
        </div>
      </div>

      <div class="form-cell">
        <label class="form-label">📝 建模配音短句（声音母本，15-50 字）</label>
        <n-input
          v-model:value="designForm.text"
          type="textarea"
          :rows="3"
          placeholder="如：风啸声起，剑影重重，这十年来，我从未有一刻忘记过这一剑的承诺。"
        />
      </div>

      <div class="form-cell">
        <label class="form-label">🎭 情绪控制描述</label>
        <n-input
          v-model:value="designForm.emotion"
          placeholder="如：非常开心、咬牙切齿、悲伤抽泣（不填默认使用基础声音）"
        />
      </div>

      <div class="form-footer">
        <label class="commit-row">
          <n-switch v-model:value="designForm.commit" />
          <span>满意后存入标准样音库</span>
          <span class="commit-tip">开启后合成完成会自动入库并带上 ✓ 样音标识</span>
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
  </div>
</template>

<script setup>
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { storeToRefs } from 'pinia';
import WarnBanner from '../components/WarnBanner.vue';
import Icon from '../components/Icon.vue';

const synthStore = useSynthStore();
const { designPresets } = storeToRefs(synthStore);
const { designForm, doDesign } = synthStore;
const capabilitiesStore = useCapabilitiesStore();
const { modelStatus } = storeToRefs(capabilitiesStore);
const { showToast } = useTasksStore();

const applyPreset = (preset) => {
  designForm.name = preset.voice_name || '';
  designForm.tone = preset.tone || '';
  designForm.text = preset.text || '';
  designForm.emotion = preset.emotion || '';
  showToast(`已套用预设: ${preset.voice_name}`, 'success');
};
</script>

<style scoped>
.tab-content-container {
  max-width: 1080px;
  margin: 0 auto;
}

/* presets */
.presets-section { display: flex; flex-direction: column; gap: var(--vf-space-3); }
.section-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-3);
}
.presets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--vf-space-3);
}
.preset-card {
  padding: var(--vf-space-3) var(--vf-space-4);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: all 0.15s var(--vf-ease);
  outline: none;
}
.preset-card:hover,
.preset-card:focus-visible {
  border-color: var(--vf-primary);
  background: var(--vf-bg-3);
  transform: translateY(-1px);
}
.preset-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--vf-primary);
}
.preset-name { font-size: 13px; font-weight: 600; color: var(--vf-text-1); }
.preset-tone { font-size: 11px; color: var(--vf-text-2); }
.preset-text {
  font-size: 11px;
  color: var(--vf-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* form */
.form-card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vf-space-4);
}
.form-cell { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; color: var(--vf-text-2); }

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
  font-size: 13px;
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
  padding: 9px 18px;
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
