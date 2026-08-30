<template></template>

<script setup>
/**
 * 全局 Naive UI API 注入组件
 * 职责：获取 useMessage 和 useDialog 并将其挂载到全局 window.$message / window.$dialog，以便在任何地方同步调用
 */
import { useMessage, useDialog } from 'naive-ui';

window.$message = useMessage();
window.$dialog = useDialog();
</script>
