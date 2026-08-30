<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN" style="height: 100%;">
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
</script>
