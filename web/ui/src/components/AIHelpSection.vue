<template>
  <div class="ai-section-container">
    <!-- 头部连通指示 -->
    <div class="ai-header">
      <div class="ai-status">
        <span class="status-dot" :class="{ 'is-online': llm.available, 'is-checking': llm.checking }"></span>
        <span class="status-text">
          AI 助手：{{ llm.available ? '已连接 (' + llm.models[0] + ')' : '未连接 (请检查中台授权)' }}
        </span>
      </div>
      <n-button :loading="llm.checking" circle size="tiny" secondary @click="checkLLM">
        🔄
      </n-button>
    </div>

    <!-- 左右分栏面板 -->
    <n-grid :cols="2" :x-gap="16" class="ai-grid">
      <!-- 生成文案 -->
      <n-grid-item>
        <div class="ai-panel">
          <div class="panel-title">✍️ 文案生成</div>
          <n-space vertical size="medium">
            <n-input 
              v-model:value="llm.genPrompt" 
              type="textarea"
              rows="3"
              placeholder="描述你想生成的主题，如：写一段介绍西湖美景的播音腔配音，带点诗意" 
            />
            <div class="form-row">
              <span class="label-text">目标字数</span>
              <n-input 
                v-model:value="llm.genWordCount" 
                placeholder="例如：100" 
                style="width: 100px;"
              />
              <n-button 
                type="primary" 
                :loading="llm.genLoading" 
                :disabled="!llm.available || !llm.genPrompt.trim()"
                @click="aiGenerate"
              >
                ✨ 生成文案
              </n-button>
            </div>
          </n-space>
        </div>
      </n-grid-item>

      <!-- 润色文案 -->
      <n-grid-item>
        <div class="ai-panel">
          <div class="panel-title">🪄 一键润色</div>
          <n-space vertical size="medium">
            <n-input 
              v-model:value="llm.polStyle" 
              placeholder="输入期望的润色风格，如：更温柔一些 / 充满悬疑感" 
            />
            <div class="polish-tip">
              将对下方文本框中的文案进行润色改写。
            </div>
            <div class="form-row flex-end">
              <n-button 
                type="primary" 
                secondary
                :loading="llm.polLoading" 
                :disabled="!llm.available"
                @click="aiPolish"
              >
                ✨ 润色文案
              </n-button>
            </div>
          </n-space>
        </div>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup>
/**
 * AI 文案助手组件
 * 职责：连接中台 LLM 接口，提供按 Prompt 生成文案以及对现有文本框内容的一键润色
 * API 来源：GET /api/llm/status, POST /api/llm/generate, POST /api/llm/polish
 */
import { inject } from 'vue';

const { llm } = inject('state');
const { checkLLM, aiGenerate, aiPolish } = inject('actions');
</script>

<style scoped>
.ai-section-container {
  border: 1px solid #2d2d30;
  border-radius: 8px;
  background-color: #1a1a1f;
  padding: 12px 16px;
  box-sizing: border-box;
  margin-bottom: 20px;
}

.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  border-bottom: 1px solid #2d2d30;
  padding-bottom: 8px;
}

.ai-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #707075;
}

.status-dot.is-online {
  background-color: #18a058;
}

.status-dot.is-checking {
  background-color: #f0a020;
  animation: pulse 1s infinite alternate;
}

@keyframes pulse {
  from { opacity: 0.4; }
  to { opacity: 1; }
}

.status-text {
  font-size: 12px;
  font-weight: 500;
  color: #a0a0a5;
}

.ai-grid {
  margin-top: 10px;
}

.ai-panel {
  background-color: #131316;
  border: 1px solid #242428;
  border-radius: 6px;
  padding: 12px;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  margin-bottom: 10px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.form-row.flex-end {
  justify-content: flex-end;
}

.label-text {
  font-size: 12px;
  color: #808085;
}

.polish-tip {
  font-size: 11px;
  color: #707075;
  margin-top: 4px;
}
</style>
