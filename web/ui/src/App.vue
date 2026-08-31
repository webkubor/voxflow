<template>
  <n-config-provider
    :theme="darkTheme"
    :theme-overrides="themeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
    style="height: 100%;"
  >
    <n-message-provider>
      <n-dialog-provider>
        <MessageApi />
        <MainLayout />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { darkTheme, zhCN, dateZhCN } from 'naive-ui';
import MessageApi from './components/MessageApi.vue';
import MainLayout from './components/MainLayout.vue';

/**
 * Naive UI 全局暗黑主题 —— 颜色从 tokens.css 读，不在组件里硬写。
 *
 * 之前这一份和 tokens.css 各自维护一套深色值，改色得改两处还容易忘。
 * 现在 token 是唯一来源：getComputedStyle 拿 CSS 变量，转一下格式塞给
 * Naive UI 的 overrides。token 改了 Naive UI 自动跟上。
 */
const readVar = (name, fallback) => {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
};

const themeOverrides = {
  common: {
    primaryColor: readVar('--vf-primary', '#6366f1'),
    primaryColorHover: readVar('--vf-primary-hover', '#818cf8'),
    primaryColorPressed: readVar('--vf-primary-active', '#4f46e5'),
    primaryColorSuppl: readVar('--vf-primary', '#6366f1'),
    successColor: readVar('--vf-ok', '#22c55e'),
    warningColor: readVar('--vf-warn', '#eab308'),
    errorColor: readVar('--vf-err', '#ef4444'),
    infoColor: readVar('--vf-info', '#5f7d95'),
    bodyColor: readVar('--vf-bg-1', '#09090c'),
    cardColor: readVar('--vf-bg-2', '#121216'),
    modalColor: readVar('--vf-bg-2', '#121216'),
    popoverColor: readVar('--vf-bg-2', '#121216'),
    inputColor: readVar('--vf-bg-3', '#18181d'),
    borderColor: readVar('--vf-border', 'rgba(255,255,255,.07)'),
    textColorBase: readVar('--vf-text-1', '#ffffff'),
    textColor1: readVar('--vf-text-1', '#ffffff'),
    textColor2: readVar('--vf-text-2', '#a1a1aa'),
    textColor3: readVar('--vf-text-3', '#71717a'),
    borderRadius: readVar('--vf-radius-sm', '8px'),
    borderRadiusSmall: readVar('--vf-radius-xs', '4px'),
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif',
  },
  Tag: { borderRadius: readVar('--vf-radius-full', '999px') },
};
</script>
