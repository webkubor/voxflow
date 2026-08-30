<template>
  <div class="tab-content-container">
    <!-- 模型未就绪警告 -->
    <div v-if="!modelStatus.base.ready && !modelStatus.base.downloading" class="warn-banner">
      ⚠️  <strong>Base 基础大模型未下载</strong> — 请在终端先跑 <code>./install.sh</code> 下载模型，否则克隆合成无法运行。
    </div>

    <!-- 顶栏：选中音色指示 -->
    <div class="selected-persona-bar">
      <span class="bar-label">当前选定音色:</span>
      <n-tag v-if="selectedPersona" type="success" size="medium" round>
        🎙️ {{ personas[selectedPersona]?.name || selectedPersona }} ({{ selectedPersona }})
      </n-tag>
      <n-tag v-else type="error" size="medium" round>
        ❌ 未选择音色 (请点击左侧音色库选择)
      </n-tag>
    </div>

    <!--
      AI 写作助手默认折叠。

      它是**给文案框服务的辅助工具**，不是流程的一步 —— 展开着占掉半个首屏，
      把真正要用的「选音色 → 填文案 → 合成」挤到屏幕以下，用户进来第一眼
      看到的是一个自己未必要用的东西。

      需要的时候点开，不需要的时候它只占一行。
    -->
    <n-collapse class="ai-help-collapse" :default-expanded-names="[]">
      <n-collapse-item name="ai">
        <template #header>
          <span class="ai-help-header">✨ AI 帮我写文案 <em>不会写就让它先出个稿</em></span>
        </template>
        <AIHelpSection />
      </n-collapse-item>
    </n-collapse>

    <!-- 历史保存文案库 -->
    <div v-if="savedScripts.length > 0" class="scripts-section">
      <div class="section-title">📂 历史保存文案</div>
      <div class="scripts-list">
        <n-tag 
          v-for="s in savedScripts" 
          :key="s.id" 
          closable 
          round 
          size="medium"
          class="script-chip"
          @click="loadScript(s)"
          @close="deleteScript(s.id)"
        >
          {{ s.title }}
        </n-tag>
      </div>
    </div>

    <!-- 合成核心表单 -->
    <div class="form-container">
      <n-form :model="cloneForm" layout="vertical">
        <n-form-item label="📝 需要合成的声音文案 (限 400 字)">
          <n-input 
            v-model:value="cloneForm.text" 
            type="textarea"
            :rows="5"
            show-count
            maxlength="400"
            placeholder="在此处输入要转成语音的文案内容..." 
          />
        </n-form-item>

        <n-grid :cols="2" :x-gap="16">
          <n-grid-item>
            <n-form-item label="🗣️ 语气描述（建议描述音色特点）">
              <n-input 
                v-model:value="cloneForm.tone" 
                placeholder="例如：沉稳的中年男子，语速平缓（默认继承音色本身描述）" 
              />
            </n-form-item>
          </n-grid-item>
          
          <n-grid-item>
            <n-form-item label="🎭 情绪标签（支持强度修饰）">
              <n-input 
                v-model:value="cloneForm.emotion" 
                placeholder="例如：happy、sad、angry（不填代表语气描述自动适配）" 
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <div class="form-actions-row">
          <n-space align="center">
            <span class="switch-label">情绪控制优先:</span>
            <n-switch v-model:value="cloneForm.emotionPriority" />
            <span class="switch-tip">开启后，模型将强力匹配情绪标签，语气描述会部分失效</span>
          </n-space>
          
          <n-space>
            <n-button secondary @click="saveScript">
              💾 保存当前文案
            </n-button>
            <n-button 
              type="primary" 
              size="large"
              :disabled="!selectedPersona || !cloneForm.text.trim() || !modelStatus.base.ready"
              @click="doClone"
            >
              🎙️ 开始声音克隆合成
            </n-button>
          </n-space>
        </div>
      </n-form>
    </div>
  </div>
</template>

<script setup>
/**
 * 声音克隆合成选项卡
 * 职责：管理并提交克隆合成任务参数，渲染历史文案库，与 AI 助手做数据绑定
 * API 来源：POST /api/clone, GET /api/scripts, POST /api/scripts 等
 */
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useVoicesStore } from '../stores/voices';
import { storeToRefs } from 'pinia';
import AIHelpSection from '../components/AIHelpSection.vue';

const voicesStore = useVoicesStore();
const synthStore = useSynthStore();
const { selectedPersona, personas } = storeToRefs(voicesStore);
const { savedScripts } = storeToRefs(synthStore);
const { cloneForm, loadScript, deleteScript, saveScript, doClone } = synthStore;
const { modelStatus } = useCapabilitiesStore();
</script>

<style scoped>
.ai-help-collapse { margin-bottom: var(--vf-space-4); }
.ai-help-header { font-size: 13px; color: var(--vf-text-2); }
.ai-help-header em { font-style: normal; margin-left: var(--vf-space-2); font-size: 12px; color: var(--vf-text-3); }

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

.selected-persona-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.bar-label {
  font-size: 13px;
  color: var(--vf-text-2);
  font-weight: 500;
}

.scripts-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  margin-bottom: 8px;
}

.scripts-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.script-chip {
  cursor: pointer;
  background-color: var(--vf-bg-3);
  border-color: var(--vf-bg-4);
  transition: background-color 0.2s, border-color 0.2s;
}

.script-chip:hover {
  background-color: #262630;
  border-color: var(--vf-ok);
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
