<template>
  <n-modal :show="show" preset="card" style="max-width: 480px" title="快捷键" @update:show="$emit('update:show', $event)">
    <div class="kbd-list">
      <div v-for="g in groups" :key="g.title" class="kbd-group">
        <div class="kbd-group-title">{{ g.title }}</div>
        <div v-for="s in g.shortcuts" :key="s.keys" class="kbd-row">
          <span class="kbd-keys">
            <kbd v-for="(k, i) in s.keys" :key="k">
              {{ k }}<span v-if="i < s.keys.length - 1" class="kbd-plus">+</span>
            </kbd>
          </span>
          <span class="kbd-desc">{{ s.desc }}</span>
        </div>
      </div>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button @click="$emit('update:show', false)">关闭</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
defineProps({ show: { type: Boolean, default: false } });
defineEmits(['update:show']);

const groups = [
  {
    title: '全局',
    shortcuts: [
      { keys: ['⌘', 'K'], desc: '聚焦搜索 / 错误日志' },
      { keys: ['/'], desc: '聚焦搜索' },
      { keys: ['?'], desc: '打开快捷键帮助' },
      { keys: ['Esc'], desc: '关闭弹窗' },
    ],
  },
  {
    title: '播放控制',
    shortcuts: [
      { keys: ['Space'], desc: '播放 / 暂停' },
      { keys: ['M'], desc: '静音 / 取消静音' },
    ],
  },
  {
    title: '导航',
    shortcuts: [
      { keys: ['1'], desc: '声音克隆' },
      { keys: ['2'], desc: '音色设计' },
      { keys: ['3'], desc: '剧本创作' },
      { keys: ['4'], desc: 'AI 音乐' },
      { keys: ['5'], desc: '作品看板' },
      { keys: ['6'], desc: '全网发行' },
      { keys: ['7'], desc: '资产库' },
    ],
  },
  {
    title: '面板',
    shortcuts: [
      { keys: ['T'], desc: '打开 / 关闭任务面板' },
      { keys: ['E'], desc: '打开 / 关闭错误日志' },
    ],
  },
];
</script>

<style scoped>
.kbd-list {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-5);
}
.kbd-group { display: flex; flex-direction: column; gap: 6px; }
.kbd-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--vf-text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.kbd-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
}
.kbd-keys { display: flex; gap: 4px; align-items: center; }
.kbd-plus { color: var(--vf-text-3); margin: 0 2px; font-size: 10px; }
kbd {
  display: inline-block;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-bottom-width: 2px;
  border-radius: var(--vf-radius-xs);
  color: var(--vf-text-1);
  font-family: ui-monospace, monospace;
  font-size: 11px;
  padding: 2px 7px;
  min-width: 22px;
  text-align: center;
}
.kbd-desc { color: var(--vf-text-2); }
</style>
