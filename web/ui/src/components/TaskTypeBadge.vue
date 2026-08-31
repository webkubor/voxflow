<template>
  <span class="task-type-badge" :class="type">
    {{ label }}
  </span>
</template>

<script setup>
/**
 * 任务类型标签 —— 后端 type 字段是自由字符串，前端按已知映射展示中文，
 * 未知的原样显示（比「未知」不丢信息）。
 */
import { computed } from 'vue';

const props = defineProps({
  type: { type: String, required: true },
});

const TYPE_LABEL = {
  clone: '克隆',
  design: '设计',
  dialogue: '剧本',
  suno: '音乐',
  publish: '发行',
  inbox: '入库',
};

const label = computed(() => TYPE_LABEL[props.type] || props.type);
</script>

<style scoped>
.task-type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--vf-radius-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  flex: none;
}
.clone { background: var(--vf-ok-soft); color: var(--vf-ok); }
.design { background: rgba(95, 125, 149, 0.15); color: var(--vf-info); }
.dialogue { background: var(--vf-warn-soft); color: var(--vf-warn); }
.suno { background: var(--vf-primary-soft); color: var(--vf-primary); }
.publish { background: rgba(234, 179, 8, 0.10); color: var(--vf-warn); }
.inbox { background: var(--vf-bg-3); color: var(--vf-text-2); }
/* 兜底色 */
.task-type-badge:not(.clone):not(.design):not(.dialogue):not(.suno):not(.publish):not(.inbox) {
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
}
</style>
