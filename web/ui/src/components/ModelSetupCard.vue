<template>
  <section class="setup-card" :class="{ 'is-downloading': prog.running || prog.downloading }">
    <div class="setup-head">
      <Icon :name="prog.running || prog.downloading ? 'download' : 'warning'" size="lg" />
      <div class="setup-title-wrap">
        <h3 class="setup-title">
          {{ prog.running || prog.downloading ? `${label}下载中` : `${label}还没下载` }}
        </h3>
        <p class="setup-sub">{{ subtitle }}</p>
      </div>
      <button
        v-if="!prog.running && !prog.downloading"
        class="dl-btn"
        :disabled="starting"
        @click="start"
      >
        <Icon name="download" size="sm" />
        <span>{{ starting ? '正在启动…' : `下载（约 ${sizeGb} GB）` }}</span>
      </button>
    </div>

    <div v-if="prog.running || prog.downloading" class="setup-progress">
      <n-progress
        type="line"
        :percentage="prog.percent || 0"
        :height="6"
        :border-radius="999"
        processing
      />
      <div class="progress-meta">
        {{ prog.downloaded_mb || 0 }} / {{ prog.total_mb || 0 }} MB
        · 下载在后台跑，<b>关掉这一页也不会中断</b>
      </div>
    </div>

    <!-- 关键的一块：不要只说他不能做什么 -->
    <div v-if="canDoNow.length" class="setup-now">
      <span class="now-label">不用等下载，现在就能用：</span>
      <button
        v-for="c in shortcuts"
        :key="c.name"
        class="now-chip"
        @click="$router.push({ name: c.name })"
      >
        {{ c.label }}
        <Icon name="arrow-right" size="sm" />
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
/**
 * 模型未就绪时的引导卡 —— 替代原来那条「请在终端运行 ./install.sh」。
 *
 * ## 为什么原来那条不够
 *
 * 全新安装打开界面，落在「声音克隆」屏：空音色库 + 灰按钮 + 一条让人回终端
 * 的警告。整屏都是死路，而这时候 AI 音乐、发行台账、运营台其实全都能用 ——
 * 只是他看不到，也没人告诉他。
 *
 * 所以这张卡做两件原来没做的事：
 *
 * 1. **就地下载**。进度读取的后端一直都有，缺的只是触发入口。下载在后台
 *    子进程里跑，关掉页面也不中断。
 * 2. **说清现在能做什么**。只讲「你缺什么」是在把人挡在门外；讲「这些不用等」
 *    才是让他能马上开始用。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { api, toMessage } from '../api';
import Icon from './Icon.vue';

const props = withDefaults(defineProps<{
  /** 'Base' 克隆/剧本要用；'VoiceDesign' 音色设计要用 */
  model?: 'Base' | 'VoiceDesign';
}>(), { model: 'Base' });

// 名字直接带上「模型」二字，模板里就不用再拼一个 —— 拼出来会变成
// 「Base 基础 模型还没下载」，中间多一个空格。
const label = computed(() => (props.model === 'Base' ? 'Base 基础模型' : 'VoiceDesign 音色设计模型'));
const sizeGb = 3.4;

const starting = ref(false);
const prog = ref<{ percent?: number; downloaded_mb?: number; total_mb?: number;
                   running?: boolean; downloading?: boolean }>({});
const canDoNow = ref<string[]>([]);

const subtitle = computed(() => {
  if (prog.value.running || prog.value.downloading) {
    return '首次下载要十几分钟。这期间下面这些功能照常可用。';
  }
  return props.model === 'Base'
    ? '本地推理的模型权重，下载后语音合成永久免费、不限量、不出本机。'
    : '只有「用一句话凭空捏音色」需要它。只想克隆已有音色的话不用下。';
});

/** 现在能用的功能 → 可点的跳转。名字对应 router 里的 tab 名。 */
const SHORTCUTS = [
  { name: 'suno', label: 'AI 音乐', match: 'AI 音乐' },
  { name: 'works', label: '作品看板', match: '作品看板' },
  { name: 'ops', label: '运营台', match: '运营台' },
];
const shortcuts = computed(() =>
  SHORTCUTS.filter((s) => canDoNow.value.some((c) => c.includes(s.match))));

const refresh = async () => {
  try {
    const d = await api.modelDownloadStatus();
    prog.value = d.models[props.model] || {};
    canDoNow.value = d.can_do_now;
  } catch { /* 查不到就保持现状，不弹错 —— 这只是一张引导卡 */ }
};

const start = async () => {
  starting.value = true;
  try {
    const r = await api.startModelDownload(props.model);
    window.$message?.info(r.detail);
    await refresh();
  } catch (e) {
    window.$message?.error(await toMessage(e));
  } finally {
    starting.value = false;
  }
};

// 下载中 5 秒一刷，闲时 20 秒 —— 没在下的时候没必要频繁问。
let timer = 0;
const tick = async () => {
  await refresh();
  timer = window.setTimeout(tick, prog.value.running || prog.value.downloading ? 5000 : 20000);
};
onMounted(tick);
onUnmounted(() => clearTimeout(timer));
</script>

<style scoped>
.setup-card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-warn-soft);
  border-left: 3px solid var(--vf-warn);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-4) var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.setup-card.is-downloading {
  border-color: var(--vf-primary-soft);
  border-left-color: var(--vf-primary);
}
.setup-head { display: flex; align-items: flex-start; gap: var(--vf-space-3); }
.setup-head > .vf-icon { color: var(--vf-warn); margin-top: 2px; flex: none; }
.is-downloading .setup-head > .vf-icon { color: var(--vf-primary); }
.setup-title-wrap { flex: 1; min-width: 0; }
.setup-title { font-size: 14px; font-weight: 600; color: var(--vf-text-1); margin: 0 0 3px; }
.setup-sub { font-size: 12px; color: var(--vf-text-2); margin: 0; line-height: 1.6; }

.dl-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: white;
  border: 1px solid white;
  color: black;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.dl-btn:hover:not(:disabled) { background: #e4e4e7; border-color: #e4e4e7; }
.dl-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.setup-progress { display: flex; flex-direction: column; gap: 6px; }
.progress-meta { font-size: 11px; color: var(--vf-text-3); }

.setup-now {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  flex-wrap: wrap;
  padding-top: var(--vf-space-3);
  border-top: 1px solid var(--vf-border);
}
.now-label { font-size: 12px; color: var(--vf-text-2); }
.now-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-1);
  font-size: 12px;
  padding: 5px 12px;
  border-radius: var(--vf-radius-full);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.now-chip:hover {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
  transform: translateY(-1px);
}
</style>
