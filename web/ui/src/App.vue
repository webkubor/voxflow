<template>
  <n-config-provider 
    :theme="darkTheme" 
    :theme-overrides="darkThemeOverrides"
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
 * Naive UI 全局暗黑主题配置覆盖。
 * 品牌色已从原本的金色统一重构为蓝紫色系列。
 * 这里的色值与 tokens.css 保持同步。
 */
const darkThemeOverrides = {
  common: {
    primaryColor: '#818cf8',        // 蓝紫主色
    primaryColorHover: '#a5b4fc',   // 悬停蓝紫
    primaryColorPressed: '#6366f1', // 按下蓝紫
    primaryColorSuppl: '#3730a3',   // 补充蓝紫
    successColor: '#6ba368',
    warningColor: '#c9973f',
    errorColor: '#b5564f',
    infoColor: '#5f7d95',
    bodyColor: '#0e0e11',
    cardColor: '#16161a',
    modalColor: '#1e1e24',
    popoverColor: '#1e1e24',
    inputColor: 'rgba(255,255,255,.04)',
    borderColor: 'rgba(255,255,255,.08)',
    textColorBase: '#ece8e1',
    textColor1: '#ece8e1',
    textColor2: '#9a958d',
    textColor3: '#6b675f',
    borderRadius: '10px',
    borderRadiusSmall: '6px',
    fontFamily: '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif',
  },
  Tag: { borderRadius: '999px' },
};
</script>
