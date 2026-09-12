<template>
  <div
    class="cover-art"
    :class="{ playing, size }"
    :style="coverStyle"
    role="img"
    :aria-label="`${title || '音频'}封面`"
  >
    <div class="cover-disc">
      <div class="cover-center"></div>
      <!-- 黑胶唱片纹理：同心圆 -->
      <div class="cover-grooves">
        <span v-for="i in 5" :key="i" class="groove"></span>
      </div>
      <!-- 中心图标 -->
      <div class="cover-icon">
        <Icon :name="icon" size="md" />
      </div>
    </div>
    <!-- 播放时的光晕 -->
    <div v-if="playing" class="cover-glow"></div>
  </div>
</template>

<script setup>
/**
 * 动态专辑封面：
 *   - 黑胶唱片造型（同心圆 + 中心图标）
 *   - 颜色按 filename 哈希取一对互补色，每次播放都不同
 *   - 播放中慢速旋转 + 外发光，停止时停转
 *
 * 真实封面图（coverUrl 传入）时优先显示真实图，叠加旋转/光晕。
 */
import { computed } from 'vue';
import Icon from '../Icon.vue';

const props = defineProps({
  /** 真实封面图 URL —— 传入时优先显示，否则用程序生成的唱片 */
  coverUrl: { type: String, default: '' },
  /** 用于哈希取色，确保不同歌曲不同色 */
  seed: { type: String, default: '' },
  /** 中心图标 */
  icon: { type: String, default: 'library' },
  /** 显示的标题（aria-label 用） */
  title: { type: String, default: '' },
  /** 是否在播放 —— 控制旋转和光晕 */
  playing: { type: Boolean, default: false },
  /** 尺寸 sm | md | lg */
  size: { type: String, default: 'md' },
});

/** 字符串 → 数字哈希（djb2 变种） */
const hash = (s) => {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i);
  return h >>> 0;
};

/** 按 seed 取一对互补色相（间隔 50°） */
const coverStyle = computed(() => {
  if (props.coverUrl) return {};
  const h = hash(props.seed || 'voxflow');
  const hue1 = h % 360;
  const hue2 = (hue1 + 50) % 360;
  return {
    backgroundImage: `
      radial-gradient(circle at 30% 30%, hsl(${hue1} 80% 60%) 0%, hsl(${hue2} 75% 35%) 100%),
      linear-gradient(135deg, hsl(${hue1} 70% 50%), hsl(${hue2} 70% 30%))
    `,
  };
});
</script>

<style scoped>
.cover-art {
  position: relative;
  border-radius: var(--vf-radius-md);
  overflow: hidden;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--vf-bg-3);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  transition: box-shadow 0.3s var(--vf-ease);
}

.cover-art.size-sm { width: 36px; height: 36px; border-radius: var(--vf-radius-sm); }
.cover-art.size-md { width: 56px; height: 56px; border-radius: var(--vf-radius-md); }
.cover-art.size-lg { width: 88px; height: 88px; border-radius: var(--vf-radius-lg); }

.cover-art.playing {
  box-shadow:
    0 6px 20px rgba(0, 0, 0, 0.5),
    0 0 24px rgba(99, 102, 241, 0.35);
}

/* 黑胶唱片 */
.cover-disc {
  position: relative;
  width: 84%;
  height: 84%;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  border: 1.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  /* 黑胶标签：彩色圆心 */
  background-image:
    radial-gradient(circle at center,
      rgba(255, 255, 255, 0.12) 0%,
      rgba(255, 255, 255, 0.04) 30%,
      rgba(0, 0, 0, 0.4) 60%
    );
  /* 播放时旋转 */
  animation: spin 8s linear infinite;
  animation-play-state: paused;
}
.cover-art.playing .cover-disc {
  animation-play-state: running;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 同心圆凹槽（伪纹理） */
.cover-grooves {
  position: absolute;
  inset: 8%;
  border-radius: 50%;
  pointer-events: none;
}
.groove {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.04);
}
.groove:nth-child(1) { inset: 8%; }
.groove:nth-child(2) { inset: 16%; }
.groove:nth-child(3) { inset: 24%; }
.groove:nth-child(4) { inset: 32%; }
.groove:nth-child(5) { inset: 40%; }

/* 唱片中心彩色标签 */
.cover-center {
  position: absolute;
  width: 30%;
  height: 30%;
  border-radius: 50%;
  background: inherit;
  background-image: inherit;
  background-color: rgba(255, 255, 255, 0.08);
  filter: brightness(0.85);
}

/* 中心图标 */
.cover-icon {
  position: relative;
  z-index: 2;
  color: rgba(255, 255, 255, 0.9);
  display: flex;
}

/* 播放时的外发光 */
.cover-glow {
  position: absolute;
  inset: -4px;
  border-radius: inherit;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.3) 0%, transparent 70%);
  animation: pulse-glow 2s ease-in-out infinite;
  pointer-events: none;
  z-index: -1;
}
@keyframes pulse-glow {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.08); }
}

/* 真实封面图模式 */
.cover-art:has(img) .cover-disc {
  background: transparent;
  border: none;
  animation: none;
}
</style>