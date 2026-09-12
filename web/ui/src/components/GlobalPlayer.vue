<template>
  <div v-if="visible" class="player-root" :class="{ 'is-minimized': minimized }">
    <!-- 完整播放器 -->
    <transition v-if="!minimized" name="slide-up">
      <div class="player-bar">
        <div class="player-grid">
          <!-- 左：封面 + 曲目信息 -->
          <div class="track-info">
            <CoverArt
              :seed="player.filename"
              :playing="isPlaying"
              :title="player.filename"
              icon="library"
              size="md"
              class="track-cover"
            />
            <div class="track-text">
              <div class="track-name" :title="player.filename">{{ player.filename || '未命名' }}</div>
              <div class="track-sub">产物试听 · 高清音频</div>
            </div>
          </div>

          <!-- 中：进度 + 光谱条 -->
          <div class="progress-area">
            <!-- 光谱条：播放中才动 -->
            <SpectrumBars
              :playing="isPlaying"
              size="md"
              class="progress-spectrum"
            />
            <div class="progress-row">
              <span class="time">{{ formatTime(currentTime) }}</span>
              <div
                class="progress-track"
                role="slider"
                tabindex="0"
                :aria-valuemin="0"
                :aria-valuemax="Math.round(duration)"
                :aria-valuenow="Math.round(currentTime)"
                :aria-label="`音频进度，${formatTime(currentTime)}/${formatTime(duration)}`"
                @click="clickProgress"
                @mousedown="startDragProgress"
                @keydown="onProgressKeydown"
              >
                <div class="progress-fill" :class="{ active: isPlaying }" :style="{ width: progressPercent + '%' }"></div>
                <div class="progress-thumb" :style="{ left: progressPercent + '%' }"></div>
              </div>
              <span class="time">{{ formatTime(duration) }}</span>
            </div>
          </div>

          <!-- 右：控制 + 音量 + 操作 -->
          <div class="right-area">
            <!-- 中央大播放按钮 -->
            <button
              class="play-toggle"
              :class="{ playing: isPlaying }"
              :aria-label="isPlaying ? '暂停' : '播放'"
              :title="isPlaying ? '暂停' : '播放'"
              @click="togglePlay"
            >
              <svg v-if="!isPlaying" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M8 5V19L19 12L8 5Z"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <rect x="6" y="5" width="4" height="14" rx="1"/>
                <rect x="14" y="5" width="4" height="14" rx="1"/>
              </svg>
            </button>

            <!-- 音量 -->
            <div class="volume-area">
              <button class="vol-btn" :title="isMuted ? '取消静音' : '静音'" @click="toggleMute">
                <Icon :name="isMuted || volume === 0 ? 'mute' : 'volume'" size="sm" />
              </button>
              <div
                class="volume-track"
                role="slider"
                tabindex="0"
                :aria-valuemin="0"
                :aria-valuemax="100"
                :aria-valuenow="Math.round((isMuted ? 0 : volume) * 100)"
                aria-label="音量"
                @click="clickVolume"
                @mousedown="startDragVolume"
                @keydown="onVolumeKeydown"
              >
                <div class="volume-fill" :style="{ width: (isMuted ? 0 : volume * 100) + '%' }"></div>
              </div>
            </div>

            <!-- 操作 -->
            <div class="actions-area">
              <a
                v-if="player.url"
                class="action-pill"
                :href="player.url"
                :download="player.filename || 'audio'"
                title="下载"
              >
                <Icon name="download" size="sm" />
              </a>
              <button class="action-icon" title="最小化" @click="minimized = true">
                <Icon name="chevron-down" size="sm" />
              </button>
              <button class="action-icon danger" title="关闭" @click="closePlayer">
                <Icon name="close" size="sm" />
              </button>
            </div>
          </div>
        </div>

        <audio
          ref="audioPlayer"
          :src="player.url"
          @timeupdate="onTimeUpdate"
          @loadedmetadata="onLoadedMetadata"
          @ended="onEnded"
          @play="isPlaying = true"
          @pause="isPlaying = false"
        ></audio>
      </div>
    </transition>

    <!-- 最小化浮窗：黑胶唱片样式 -->
    <button
      v-else
      class="player-mini"
      :class="{ playing: isPlaying }"
      title="展开播放器"
      @click="minimized = false"
    >
      <CoverArt
        :seed="player.filename"
        :playing="isPlaying"
        :title="player.filename"
        icon="library"
        size="sm"
      />
      <SpectrumBars
        v-if="isPlaying"
        :playing="true"
        size="sm"
        color="white"
        class="mini-eq"
      />
      <span v-else class="mini-pause-icon">▶</span>
    </button>
  </div>
</template>

<script setup>
/**
 * 全局播放器（重做版）。
 *
 * ## 架构
 *
 * 通过 audioBus 注册 'global-player' 频道 —— 播这首歌时自动暂停 PersonaSidebar
 * 试听，反之亦然。同一时间只有一首音频在响。
 *
 * ## 视觉升级（相比上一版）
 *
 *   - 专辑封面（CoverArt）：黑胶唱片造型，文件名哈希取色，播放时慢转 + 发光
 *   - 光谱条（SpectrumBars）：28 根 bar 错峰动画，纯 CSS 无音频分析开销
 *   - 中央大播放按钮：白底圆形 + 阴影 hover scale，播放时变紫
 *   - 进度条：保留流光效果，hover 显示 thumb
 *   - 最小化浮窗：60×60 黑胶唱片，封面跟着转
 *   - hover/transition 全部 token 化的 var(--vf-ease) cubic-bezier
 */
import { ref, watch, nextTick, onMounted, onBeforeUnmount, computed } from 'vue';
import { useRoute } from 'vue-router';
import { audioBus } from '../stores/audioBus';
import { useLibraryStore } from '../stores/library';
import { useTasksStore } from '../stores/tasks';
import Icon from './Icon.vue';
import CoverArt from './player/CoverArt.vue';
import SpectrumBars from './player/SpectrumBars.vue';

const { player, closePlayer } = useLibraryStore();
const { showToast } = useTasksStore();
const audioPlayer = ref(null);

const visible = computed(() => !!player.url);
const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const progressPercent = ref(0);
const isDraggingProgress = ref(false);
const volume = ref(0.8);
const isMuted = ref(false);
const minimized = ref(false);

const route = useRoute();

const formatTime = (secs) => {
  if (isNaN(secs) || secs === Infinity) return '00:00';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

const togglePlay = () => {
  if (!audioPlayer.value) return;
  if (isPlaying.value) {
    audioPlayer.value.pause();
  } else {
    audioPlayer.value.play().catch(() => {
      showToast('试听音频播放失败', 'error');
    });
  }
};

const toggleMute = () => {
  isMuted.value = !isMuted.value;
  if (audioPlayer.value) audioPlayer.value.muted = isMuted.value;
};

const onTimeUpdate = () => {
  if (isDraggingProgress.value || !audioPlayer.value) return;
  currentTime.value = audioPlayer.value.currentTime;
  if (duration.value > 0) progressPercent.value = (currentTime.value / duration.value) * 100;
};

const onLoadedMetadata = () => {
  if (audioPlayer.value) duration.value = audioPlayer.value.duration;
};

const onEnded = () => {
  isPlaying.value = false;
  currentTime.value = 0;
  progressPercent.value = 0;
};

const seekTo = (percent) => {
  const p = Math.max(0, Math.min(1, percent));
  progressPercent.value = p * 100;
  currentTime.value = p * duration.value;
  if (audioPlayer.value) audioPlayer.value.currentTime = currentTime.value;
};

const clickProgress = (e) => {
  if (!duration.value) return;
  const rect = e.currentTarget.getBoundingClientRect();
  seekTo((e.clientX - rect.left) / rect.width);
};

const startDragProgress = (e) => {
  if (!duration.value) return;
  isDraggingProgress.value = true;
  clickProgress(e);
  const onMove = (ev) => clickProgress({ currentTarget: e.currentTarget, clientX: ev.clientX });
  const onUp = () => {
    isDraggingProgress.value = false;
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  };
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
};

const onProgressKeydown = (e) => {
  if (!duration.value) return;
  const step = e.shiftKey ? 10 : 5;
  if (e.key === 'ArrowLeft') { seekTo((currentTime.value - step) / duration.value); e.preventDefault(); }
  else if (e.key === 'ArrowRight') { seekTo((currentTime.value + step) / duration.value); e.preventDefault(); }
  else if (e.key === 'Home') { seekTo(0); e.preventDefault(); }
  else if (e.key === 'End') { seekTo(1); e.preventDefault(); }
  else if (e.key === ' ' || e.key === 'Spacebar') { togglePlay(); e.preventDefault(); }
};

const setVolume = (v) => {
  const clamped = Math.max(0, Math.min(1, v));
  volume.value = clamped;
  isMuted.value = clamped === 0;
  if (audioPlayer.value) {
    audioPlayer.value.volume = clamped;
    audioPlayer.value.muted = clamped === 0;
  }
};

const clickVolume = (e) => {
  const rect = e.currentTarget.getBoundingClientRect();
  setVolume((e.clientX - rect.left) / rect.width);
};

const startDragVolume = (e) => {
  clickVolume(e);
  const onMove = (ev) => clickVolume({ currentTarget: e.currentTarget, clientX: ev.clientX });
  const onUp = () => {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  };
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
};

const onVolumeKeydown = (e) => {
  const step = e.shiftKey ? 0.1 : 0.05;
  if (e.key === 'ArrowLeft') { setVolume(volume.value - step); e.preventDefault(); }
  else if (e.key === 'ArrowRight') { setVolume(volume.value + step); e.preventDefault(); }
  else if (e.key === 'Home') { setVolume(0); e.preventDefault(); }
  else if (e.key === 'End') { setVolume(1); e.preventDefault(); }
};

// 新曲目 → 展开 + 播放
watch(
  () => player.url,
  async (newUrl) => {
    if (!newUrl) return;
    minimized.value = false;
    isPlaying.value = true;
    await nextTick();
    if (audioPlayer.value) {
      audioPlayer.value.load();
      audioPlayer.value.play().catch(() => {
        showToast('已加载音频，点击播放按钮试听', 'info');
        isPlaying.value = false;
      });
    }
  },
);

// 路由切到浏览型 tab 时暂停；audioBus 会自动暂停 persona-preview
let stopRouteWatch = null;
onMounted(() => {
  if (audioPlayer.value) {
    audioBus.register('global-player', audioPlayer.value, {
      onPlay: () => { isPlaying.value = true; },
      onPause: () => { isPlaying.value = false; },
    });
  }
  stopRouteWatch = watch(
    () => route.name,
    (newName) => {
      if (!isPlaying.value || !audioPlayer.value) return;
      const browseTabs = new Set(['library', 'works', 'publish']);
      if (browseTabs.has(newName)) audioPlayer.value.pause();
    },
  );
});
onBeforeUnmount(() => {
  stopRouteWatch?.();
  audioBus.unregister('global-player');
});

watch(visible, (v) => {
  if (!v && audioPlayer.value) audioPlayer.value.pause();
});

// 给父级全局快捷键调用
defineExpose({ togglePlay, toggleMute });
</script>

<style scoped>
/* ── 容器 ── */
.player-root {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: var(--vf-player-h);
  z-index: 90;
  pointer-events: none;
}
.player-root > * { pointer-events: auto; }

/* ── 完整播放器 ── */
.player-bar {
  height: 100%;
  background: rgba(10, 10, 14, 0.82);
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  border-top: 1px solid var(--vf-border-strong);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 -8px 24px rgba(0, 0, 0, 0.5);
  padding: 0 var(--vf-space-6);
}

.player-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 1.4fr minmax(240px, 1fr);
  align-items: center;
  gap: var(--vf-space-5);
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

/* ── 左：曲目信息 ── */
.track-info {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  min-width: 0;
}
.track-cover { flex: none; }
.track-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.track-name {
  font-size: 14px;
  font-weight: 600;
  color: white;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}
.track-sub {
  font-size: 11px;
  color: var(--vf-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 中：光谱 + 进度 ── */
.progress-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.progress-spectrum {
  color: var(--vf-primary);
  height: 18px;
  opacity: 0.85;
}
.progress-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  width: 100%;
}
.time {
  font-size: 11px;
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
  width: 42px;
  text-align: center;
}
.progress-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: var(--vf-radius-full);
  position: relative;
  cursor: pointer;
  outline: none;
  transition: height 0.15s var(--vf-ease);
}
.progress-track:hover,
.progress-track:focus-visible {
  height: 6px;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg,
    var(--vf-primary-active) 0%,
    var(--vf-primary) 35%,
    var(--vf-primary-hover) 70%,
    white 100%);
  border-radius: var(--vf-radius-full);
  position: absolute;
  left: 0;
  top: 0;
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.5);
}
.progress-fill.active {
  background-size: 200% 100%;
  animation: shimmer 2.5s linear infinite;
}
@keyframes shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}
.progress-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: white;
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%) scale(0);
  box-shadow:
    0 0 0 2px rgba(99, 102, 241, 0.5),
    0 0 8px rgba(255, 255, 255, 0.8);
  transition: transform 0.15s var(--vf-ease);
}
.progress-track:hover .progress-thumb,
.progress-track:focus-visible .progress-thumb {
  transform: translate(-50%, -50%) scale(1.3);
}

/* ── 右：控制 ── */
.right-area {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--vf-space-4);
}

/* 中央大播放按钮 */
.play-toggle {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: white;
  color: black;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  transition: all 0.18s var(--vf-ease);
}
.play-toggle:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 20px rgba(255, 255, 255, 0.35);
}
.play-toggle:active { transform: scale(0.96); }
.play-toggle.playing {
  background: var(--vf-primary);
  color: white;
  box-shadow:
    0 0 0 4px rgba(99, 102, 241, 0.15),
    0 4px 16px rgba(99, 102, 241, 0.5);
}

/* 音量 */
.volume-area {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  width: 110px;
}
.vol-btn {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  padding: 4px;
  display: flex;
  border-radius: var(--vf-radius-xs);
  transition: color 0.15s, background 0.15s;
}
.vol-btn:hover {
  color: white;
  background: var(--vf-bg-hover);
}
.volume-track {
  flex: 1;
  height: 3px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: var(--vf-radius-full);
  position: relative;
  cursor: pointer;
  outline: none;
  transition: height 0.15s;
}
.volume-track:hover,
.volume-track:focus-visible { height: 5px; }
.volume-fill {
  height: 100%;
  background: rgba(255, 255, 255, 0.7);
  border-radius: var(--vf-radius-full);
  transition: background 0.15s;
}
.volume-track:hover .volume-fill { background: white; }

/* 操作按钮 */
.actions-area {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}
.action-pill,
.action-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--vf-radius-sm);
  font-size: 12px;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.action-pill {
  width: 32px;
  height: 32px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: white;
}
.action-pill:hover {
  background: white;
  color: black;
  transform: translateY(-1px);
}
.action-icon {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid transparent;
  color: var(--vf-text-3);
}
.action-icon:hover {
  color: var(--vf-text-1);
  background: var(--vf-bg-hover);
}
.action-icon.danger:hover {
  color: var(--vf-err);
  background: var(--vf-err-soft);
}

/* ── 最小化浮窗（60×60 黑胶）── */
.player-mini {
  position: fixed;
  right: var(--vf-space-3);
  bottom: var(--vf-space-3);
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: transparent;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  transition: transform 0.2s var(--vf-ease);
}
.player-mini:hover { transform: scale(1.05) translateY(-2px); }
.player-mini.playing {
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.5),
    0 0 24px rgba(99, 102, 241, 0.4);
}
.mini-eq {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 24px;
  height: 14px;
  background: rgba(0, 0, 0, 0.65);
  border-radius: var(--vf-radius-full);
  padding: 0 2px;
  color: var(--vf-primary);
}
.mini-pause-icon {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 24px;
  height: 24px;
  background: rgba(0, 0, 0, 0.65);
  border-radius: 50%;
  color: var(--vf-text-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}

/* ── 进场动画 ── */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.25s var(--vf-ease), opacity 0.25s;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .player-grid {
    grid-template-columns: 1fr auto;
    gap: var(--vf-space-3);
  }
  .progress-area { display: none; }
}
@media (max-width: 600px) {
  .volume-area, .actions-area { display: none; }
  .track-text { max-width: 160px; }
}
</style>