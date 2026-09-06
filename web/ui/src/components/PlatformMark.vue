<template>
  <span
    class="plat-mark"
    :class="[`is-${platform}`, `sz-${size}`]"
    role="img"
    :aria-label="label"
  >
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <!-- 汽水：青绿底 + 水滴。字节这款产品的辨识就是「汽水/水」。 -->
      <g v-if="platform === 'qishui'">
        <circle cx="12" cy="12" r="12" fill="currentColor" />
        <path
          d="M12 4.8s-5.2 6.4-5.2 9.6a5.2 5.2 0 1 0 10.4 0C17.2 11.2 12 4.8 12 4.8z"
          fill="#041918"
        />
        <path
          d="M10.4 13.1c.5-1.6 2.1-3.2 2.1-3.2"
          fill="none"
          stroke="#9ff8f0"
          stroke-width="1.3"
          stroke-linecap="round"
        />
      </g>
      <!-- 网易云：红底 + 云和音符。红是这套品牌几乎唯一的颜色。 -->
      <g v-else-if="platform === 'netease'">
        <circle cx="12" cy="12" r="12" fill="currentColor" />
        <path
          d="M7.2 13.6c0-2 1.6-3.4 3.4-3.4.4 0 .8.1 1.1.2.5-1.3 1.8-2.2 3.3-2.2 1.9 0 3.4 1.5 3.4 3.3 0 .2 0 .4-.1.6 1.2.4 2 1.5 2 2.8 0 1.6-1.3 3-3 3H8.8c-1.6 0-2.8-1.3-2.8-2.9 0-.6.2-1.2.5-1.6z"
          fill="#fff"
        />
        <path
          d="M13.2 10.2v5.1a1.5 1.5 0 1 1-1.1-1.45V11.6l3.4-.7v1.35"
          fill="none"
          stroke="#EC4141"
          stroke-width="1.15"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </g>
      <!-- QQ 音乐：绿底 + 双八分音符。 -->
      <g v-else-if="platform === 'tencent'">
        <circle cx="12" cy="12" r="12" fill="currentColor" />
        <path
          d="M10.2 8.2v6.05a1.7 1.7 0 1 1-1.25-1.64V9.35l6.1-1.25v5.95A1.7 1.7 0 1 1 13.8 12.4V8.55l-3.6.75z"
          fill="#fff"
        />
      </g>
      <g v-else>
        <circle cx="12" cy="12" r="12" fill="currentColor" />
        <path d="M9 17.2V8.4l8-1.4v8.4" fill="none" stroke="#fff" stroke-width="1.5" />
        <circle cx="8.2" cy="17.2" r="1.7" fill="#fff" />
        <circle cx="15.8" cy="15.4" r="1.7" fill="#fff" />
      </g>
    </svg>
  </span>
</template>

<script setup lang="ts">
/**
 * 发行平台品牌标。汽水 / 网易云 / QQ 三套，颜色跟品牌走、不跟主题翻转。
 *
 * 用简化几何而不是官方 logo 文件：官方标是商标，这个仪表盘只需要
 * 「一眼分出三个平台」。加平台时这里加一个分支，并在 tokens.css 补颜色。
 */
import { computed } from 'vue';
import type { PlatformKey } from '../types/api';

const LABELS: Record<string, string> = {
  qishui: '汽水音乐',
  netease: '网易云音乐',
  tencent: 'QQ音乐',
};

const props = defineProps<{
  platform: PlatformKey | string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}>();

const size = computed(() => props.size || 'md');
const label = computed(() => LABELS[props.platform] || props.platform);
</script>

<style scoped>
.plat-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  border-radius: 50%;
  overflow: hidden;
  line-height: 0;
}
.plat-mark svg { display: block; width: 100%; height: 100%; }
.sz-sm { width: 16px; height: 16px; }
.sz-md { width: 20px; height: 20px; }
.sz-lg { width: 28px; height: 28px; }
.sz-xl { width: 40px; height: 40px; }
.is-qishui { color: var(--vf-plat-qishui); }
.is-netease { color: var(--vf-plat-netease); }
.is-tencent { color: var(--vf-plat-tencent); }
</style>
