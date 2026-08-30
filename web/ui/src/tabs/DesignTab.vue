<template>
  <div class="tab-content-container">
    <!-- 模型未就绪警告 -->
    <div v-if="!modelStatus.design.ready && !modelStatus.design.downloading" class="warn-banner">
      ⚠️  <strong>VoiceDesign 设计大模型未下载</strong> — 请在终端先跑 <code>./install.sh</code>（选择下载音色设计大模型），否则音色设计功能无法运行。
    </div>

    <!-- 预设配方网格 -->
    <div v-if="designPresets.length > 0" class="presets-section">
      <div class="section-title">✨ 一键套用预设声音配方</div>
      <n-grid :cols="4" :x-gap="12" :y-gap="12" class="presets-grid">
        <n-grid-item v-for="(p, idx) in designPresets" :key="idx">
          <div class="preset-card" @click="applyPreset(p)">
            <div class="preset-name">{{ p.voice_name }}</div>
            <div class="preset-tone">{{ p.tone }}</div>
            <div class="preset-text" :title="p.text">短句: {{ p.text }}</div>
          </div>
        </n-grid-item>
      </n-grid>
    </div>

    <!-- 音色设计核心表单 -->
    <div class="form-container">
      <n-form :model="designForm" layout="vertical">
        <n-grid :cols="2" :x-gap="16">
          <n-grid-item>
            <n-form-item label="🎙️ 新音色名称">
              <n-input 
                v-model:value="designForm.name" 
                placeholder="例如：冷酷刺客 / 温柔主播" 
              />
            </n-form-item>
          </n-grid-item>
          
          <n-grid-item>
            <n-form-item label="🗣️ 语气描述（用形容词精准描述）">
              <n-input 
                v-model:value="designForm.tone" 
                placeholder="例如：声音低沉、沙哑、冰冷，语速缓慢" 
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <n-form-item label="📝 建模配音短句（生成此音色的声音母本短语）">
          <n-input 
            v-model:value="designForm.text" 
            type="textarea"
            :rows="3"
            placeholder="在此处输入 15-50 字的建模样本台词，要求读音多变。例如：风啸声起，剑影重重，这十年来，我从未有一刻忘记过这一剑的承诺。" 
          />
        </n-form-item>

        <n-form-item label="🎭 情绪控制描述">
          <n-input 
            v-model:value="designForm.emotion" 
            placeholder="例如：非常开心、咬牙切齿、悲伤抽泣（不填默认使用基础声音）" 
          />
        </n-form-item>

        <div class="form-actions-row">
          <n-space align="center">
            <span class="switch-label">满意后存入标准样音库:</span>
            <n-switch v-model:value="designForm.commit" />
            <span class="switch-tip">开启后，合成完成后该音色会自动入库并带上“✓ 样音”标识</span>
          </n-space>
          
          <n-button 
            type="primary" 
            size="large"
            :disabled="!designForm.name.trim() || !designForm.text.trim() || !modelStatus.design.ready"
            @click="doDesign"
          >
            🎨 合成并设计音色
          </n-button>
        </div>
      </n-form>
    </div>
  </div>
</template>

<script setup>
/**
 * 音色设计选项卡
 * 职责：展示设计模型就绪度，渲染音色预设网格，提供套用逻辑并提交音色设计参数
 * API 来源：POST /api/design, /api/personas (design_presets 字段)
 */
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { storeToRefs } from 'pinia';

const synthStore = useSynthStore();
const { designPresets } = storeToRefs(synthStore);
const { designForm, doDesign } = synthStore;
const { modelStatus } = useCapabilitiesStore();
const { showToast } = useTasksStore();

// 一键套用预设配方
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
  display: flex;
  flex-direction: column;
  height: 100%;
}

.warn-banner {
  background-color: rgba(240, 160, 32, 0.1);
  border: 1px solid var(--vf-gold);
  border-radius: 6px;
  color: var(--vf-gold);
  padding: 10px 15px;
  font-size: 13px;
  margin-bottom: 16px;
}

.presets-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  margin-bottom: 8px;
}

.presets-grid {
  margin-top: 8px;
}

.preset-card {
  border: 1px solid var(--vf-bg-4);
  border-radius: 6px;
  background-color: var(--vf-bg-1);
  padding: 10px;
  cursor: pointer;
  height: 90px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: border-color 0.2s, background-color 0.2s;
}

.preset-card:hover {
  border-color: var(--vf-ok);
  background-color: var(--vf-bg-3);
}

.preset-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.preset-tone {
  font-size: 11px;
  color: var(--vf-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preset-text {
  font-size: 11px;
  color: var(--vf-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.form-container {
  background-color: var(--vf-bg-1);
  border: 1px solid var(--vf-bg-4);
  border-radius: 8px;
  padding: 20px;
}

.form-actions-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  border-top: 1px solid var(--vf-bg-4);
  padding-top: 16px;
}

.switch-label {
  font-size: 13px;
  color: var(--vf-text-1);
}

.switch-tip {
  font-size: 11px;
  color: var(--vf-text-3);
}
</style>
