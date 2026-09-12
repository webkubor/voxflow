<template>
  <div class="spectrum" :class="{ playing, size }" :style="{ color }">
    <span
      v-for="i in barCount"
      :key="i"
      class="bar"
      :style="{ animationDelay: `-${(i * 0.07).toFixed(2)}s`, animationDuration: `${(0.6 + (i % 5) * 0.1).toFixed(2)}s` }"
    ></span>
  </div>
</template>

<script setup>
/**
 * 光谱条 —— 纯 CSS 动画，假装在根据音频跳舞。
 *
 * 没用 Web Audio API + AnalyserNode 真的取 FFT：
 *   - 真分析需要 AudioContext + MediaElementSource，加复杂度
 *   - CSS 假动画视觉上够「在动」感感」，用户看不出区别
 *   - 不增加包体
 *
 * 每根 bar 用 cubic-bezier 错峰动画，停止时全部归零高度。
 */
import { computed } from 'vue';

const props = defineProps({
  playing: { type: Boolean, default: false },
  size: { type: String, default: 'md' }, // sm | md | lg
  /** 颜色（继承自父级 currentColor） */
  color: { type: String, default: '' },
  /** bar 数量 */
  barCount: { type: Number, default: 28 },
});
</script>

<style scoped>
.spectrum {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  height: 24px;
  flex: none;
}

.spectrum.size-sm { height: 14px; gap: 1.5px; }
.spectrum.size-lg { height: 36px; gap: 3px; }

.bar {
  width: 2.5px;
  height: 4px;
  background: currentColor;
  border-radius: var(--vf-radius-full);
  opacity: 0.7;
  /* 默认停止态：高度归零 */
  animation: spectrum-bounce 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  animation-play-state: paused;
}

.spectrum.size-sm .bar { width: 2px; }
.spectrum.size-lg .bar { width: 3.5px; }

/* 播放中才动 */
.spectrum.playing .bar {
  animation-play-state: running;
}

/* 错峰动画 —— 每根 bar 起点不同、高度不同，模仿真实频谱 */
@keyframes spectrum-bounce {
  0% { height: 4px; }
  20% { height: 18px; }
  40% { height: 8px; }
  60% { height: 22px; }
  80% { height: 12px; }
  100% { height: 4px; }
}
</style>