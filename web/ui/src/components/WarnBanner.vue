<template>
  <div class="warn-banner" :class="`type-${type}`" role="status" :aria-label="title">
    <span class="warn-icon" aria-hidden="true">{{ icon }}</span>
    <div class="warn-content">
      <div class="warn-title">{{ title }}</div>
      <div v-if="hint" class="warn-hint">{{ hint }}</div>
      <slot />
    </div>
    <div v-if="action" class="warn-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  /** 语义类型决定颜色与图标 —— 颜色全走 token，不要再在调用处覆盖 */
  type: { type: String, default: 'info' },
  /** 主标题：粗体一行让人扫一眼抓住重点 */
  title: { type: String, required: true },
  /** 副标题/解释：可能含 code 标签，HTML 由调用方提供 */
  hint: { type: String, default: '' },
  /** 显示右侧操作按钮区 */
  action: { type: Boolean, default: false },
});

const ICONS = {
  warn: '⚠️',
  error: '❌',
  info: 'ℹ️',
  success: '✅',
};
const icon = computed(() => ICONS[props.type] || ICONS.info);
</script>

<style scoped>
.warn-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3) var(--vf-space-4);
  border: 1px solid var(--vf-border);
  border-left-width: 3px;
  border-radius: var(--vf-radius-sm);
  font-size: 13px;
  line-height: 1.5;
}
.warn-icon {
  font-size: 16px;
  flex: none;
  line-height: 1.4;
}
.warn-content {
  flex: 1;
  min-width: 0;
}
.warn-title {
  font-weight: 600;
  color: var(--vf-text-1);
}
.warn-hint {
  margin-top: 2px;
  color: var(--vf-text-2);
  font-size: 12px;
}
.warn-hint :deep(code) {
  padding: 1px 5px;
  border-radius: var(--vf-radius-xs);
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  font-size: 11px;
}
.warn-action {
  flex: none;
}

/* 类型分支 —— 左边色条 + 浅色底，三档够用 */
.type-warn {
  border-left-color: var(--vf-warn);
  background: var(--vf-warn-soft);
}
.type-warn .warn-title { color: var(--vf-warn); }

.type-error {
  border-left-color: var(--vf-err);
  background: var(--vf-err-soft);
}
.type-error .warn-title { color: var(--vf-err); }

.type-info {
  border-left-color: var(--vf-info);
  background: var(--vf-bg-2);
}

.type-success {
  border-left-color: var(--vf-ok);
  background: var(--vf-ok-soft);
}
.type-success .warn-title { color: var(--vf-ok); }
</style>
