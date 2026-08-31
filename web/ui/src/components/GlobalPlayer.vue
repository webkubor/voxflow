<template>
  <div v-if="visible" class="player-root" :class="{ 'is-minimized': minimized }">
    <!-- 完整播放器 -->
    <transition v-if="!minimized" name="slide-up">
      <div class="player-bar">
        <div class="player-grid">
          <!-- 左：曲目信息 -->
          <div class="track-info">
            <button
              class="play-toggle"
              :class="{ playing: isPlaying }"
              :aria-label="isPlaying ? '暂停' : '播放'"
              :title="isPlaying ? '暂停' : '播放'"
              @click="togglePlay"
            >
              <svg v-if="!isPlaying" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M8 5V19L19 12L8 5Z"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/>
              </svg>
            </button>
            <div v-if="isPlaying" class="equalizer" aria-hidden="true">
              <span></span><span></span><span></span><span></span>
            </div>
            <div v-else class="music-note" aria-hidden="true">♪</div>
            <div class="track-text">
              <div class="track-name" :title="player.filename">{{ player.filename }}</div>
              <div class="track-sub">产物试听 · 高清音频</div>
            </div>
          </div>

          <!-- 中：进度条 -->
          <div class="progress-area">
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

          <!-- 右：音量 + 操作 -->
          <div class="right-area">
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

            <div class="actions-area">
              <a class="action-pill" :href="player.url" :download="player.filename" title="下载">
                <Icon name="download" size="sm" />
                <span>下载</span>
              </a>
              <button class="action-icon" title="最小化" @click="minimized = true">
                <Icon name="chevron-down" size="sm" />
              </button>
              <button class="action-icon" title="关闭" @click="closePlayer">
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

    <!-- 最小化条：56x56 浮窗，右下角 -->
    <button
      v-else
      class="player-mini"
      :class="{ playing: isPlaying }"
      title="展开播放器"
      @click="minimized = false"
    >
      <div class="mini-icon">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M8 5V19L19 12L8 5Z" v-if="!isPlaying"/>
          <g v-else>
            <rect x="6" y="5" width="4" height="14"/>
            <rect x="14" y="5" width="4" height="14"/>
          </g>
        </svg>
      </div>
      <div v-if="isPlaying" class="mini-eq" aria-hidden="true">
        <span></span><span></span><span></span>
      </div>
    </button>
  </div>
</template>

<script setup>
/**
 * 全局播放器。
 *
 * ## 最小化
 *
 * 之前关掉就找不到入口。改成「最小化」：缩成右下角 56×56 浮窗，
 * 还在播的音频不会被打断；想找回来点一下就回弹成完整播放器。
 * 完全关闭时（closePlayer）才走 library store 把 player 清空。
 *
 * ## 路由切暂停
 *
 * 用户切到「资产库」浏览时还听旧音频，体验割裂。监听路由变化：
 * 切到 LibraryTab（浏览列表）时自动暂停，但其他 Tab 不主动暂停 —
 * 创作 Tab 时用户往往一边听参考音一边写文案。
 *
 * ## 键盘可达
 *
 * 进度条 / 音量条加 role="slider" + tabindex + 方向键调节，
 * 不再用鼠标硬点。
 */
import { ref, watch, nextTick, onMounted, onBeforeUnmount, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useLibraryStore } from '../stores/library';
import { useTasksStore } from '../stores/tasks';
import Icon from './Icon.vue';

const { player, closePlayer } = useLibraryStore();
const { showToast } = useTasksStore();
const audioPlayer = ref(null);

const visible = computed(() => !!player.value?.url);

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

/** 键盘调进度：← / → 5 秒，Home / End 跳头尾 */
const onProgressKeydown = (e) => {
  if (!duration.value) return;
  const step = e.shiftKey ? 10 : 5;
  if (e.key === 'ArrowLeft') {
    seekTo((currentTime.value - step) / duration.value);
    e.preventDefault();
  } else if (e.key === 'ArrowRight') {
    seekTo((currentTime.value + step) / duration.value);
    e.preventDefault();
  } else if (e.key === 'Home') {
    seekTo(0);
    e.preventDefault();
  } else if (e.key === 'End') {
    seekTo(1);
    e.preventDefault();
  } else if (e.key === ' ' || e.key === 'Spacebar') {
    togglePlay();
    e.preventDefault();
  }
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
  if (e.key === 'ArrowLeft') {
    setVolume(volume.value - step);
    e.preventDefault();
  } else if (e.key === 'ArrowRight') {
    setVolume(volume.value + step);
    e.preventDefault();
  } else if (e.key === 'Home') {
    setVolume(0);
    e.preventDefault();
  } else if (e.key === 'End') {
    setVolume(1);
    e.preventDefault();
  }
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

// 路由变化：切到「资产库 / 看板」这种浏览型 tab 时暂停
// 创作型 tab（克隆 / 设计 / 剧本 / 音乐）用户往往一边听一边写，不主动打断
let stopRouteWatch = null;
onMounted(() => {
  stopRouteWatch = watch(
    () => route.name,
    (newName) => {
      if (!isPlaying.value || !audioPlayer.value) return;
      const PAUSE_ON_ROUTE = new Set(['library', 'works', 'publish']);
      if (PAUSE_ON_ROUTE.has(newName)) {
        audioPlayer.value.pause();
      }
    },
  );
});
onBeforeUnmount(() => {
  if (stopRouteWatch) stopRouteWatch();
});

// 关闭时记得停掉音频
watch(visible, (v) => {
  if (!v && audioPlayer.value) audioPlayer.value.pause();
});
</script>

<style scoped>
.player-root {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: var(--vf-player-h);
  z-index: 90;
  pointer-events: none;
}
.player-root > * {
  pointer-events: auto;
}

/* 完整播放器 */
.player-bar {
  height: 100%;
  background: rgba(10, 10, 14, 0.78);
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  border-top: 1px solid var(--vf-border-strong);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 -8px 24px rgba(0, 0, 0, 0.5);
  padding: 0 var(--vf-space-6);
}

.player-grid {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) 2fr minmax(200px, 1fr);
  align-items: center;
  gap: var(--vf-space-4);
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

/* 曲目信息 */
.track-info {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  min-width: 0;
}
.play-toggle {
  background: white;
  border: none;
  color: black;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex: none;
  transition: all 0.15s var(--vf-ease);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}
.play-toggle:hover {
  transform: scale(1.08);
  box-shadow: 0 0 16px rgba(255, 255, 255, 0.4);
}
.play-toggle.playing {
  box-shadow: 0 0 14px rgba(99, 102, 241, 0.5);
}
.equalizer {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 16px;
}
.equalizer span {
  width: 2px;
  background: white;
  border-radius: 99px;
  animation: eq-bounce 0.8s infinite alternate ease-in-out;
  box-shadow: 0 0 4px rgba(255, 255, 255, 0.6);
}
.equalizer span:nth-child(1) { height: 5px; animation-delay: 0s; }
.equalizer span:nth-child(2) { height: 14px; animation-delay: 0.15s; }
.equalizer span:nth-child(3) { height: 8px; animation-delay: 0.3s; }
.equalizer span:nth-child(4) { height: 12px; animation-delay: 0.45s; }
.music-note { font-size: 14px; color: var(--vf-text-2); }
@keyframes eq-bounce {
  from { height: 3px; }
  to { height: 14px; }
}

.track-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.track-name {
  font-size: 13px;
  font-weight: 600;
  color: white;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.track-sub {
  font-size: 11px;
  color: var(--vf-text-3);
}

/* 进度条 */
.progress-area {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}
.time {
  font-size: 11px;
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
  width: 40px;
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
  transition: height 0.15s;
}
.progress-track:hover,
.progress-track:focus-visible {
  height: 6px;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--vf-primary-active) 0%, var(--vf-primary) 35%, var(--vf-primary-hover) 70%, white 100%);
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
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.5), 0 0 8px rgba(255, 255, 255, 0.8);
  transition: transform 0.15s var(--vf-ease);
}
.progress-track:hover .progress-thumb,
.progress-track:focus-visible .progress-thumb {
  transform: translate(-50%, -50%) scale(1.3);
}

/* 右区 */
.right-area {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--vf-space-3);
}
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
  padding: 2px;
  display: flex;
  transition: color 0.15s;
}
.vol-btn:hover { color: white; }
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
.volume-track:focus-visible {
  height: 5px;
}
.volume-fill {
  height: 100%;
  background: rgba(255, 255, 255, 0.7);
  border-radius: var(--vf-radius-full);
  transition: background 0.15s;
}
.volume-track:hover .volume-fill {
  background: white;
}

.actions-area {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}
.action-pill {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: white;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 4px 10px;
  border-radius: var(--vf-radius-sm);
  text-decoration: none;
  transition: all 0.15s;
}
.action-pill:hover {
  background: white;
  color: black;
  border-color: white;
}
.action-icon {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  width: 28px;
  height: 28px;
  border-radius: var(--vf-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.action-icon:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
}

/* 最小化态 */
.player-mini {
  position: fixed;
  right: var(--vf-space-3);
  bottom: var(--vf-space-3);
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(10, 10, 14, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--vf-border-strong);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: var(--vf-shadow-elevated);
  transition: all 0.2s var(--vf-ease);
}
.player-mini:hover {
  transform: translateY(-2px);
  border-color: var(--vf-primary);
}
.player-mini.playing {
  border-color: var(--vf-primary);
  box-shadow: 0 0 16px rgba(99, 102, 241, 0.4);
}
.mini-icon { display: flex; }
.mini-eq {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  gap: 1.5px;
  align-items: flex-end;
  height: 12px;
}
.mini-eq span {
  width: 2px;
  background: var(--vf-primary);
  border-radius: 99px;
  animation: eq-bounce 0.8s infinite alternate ease-in-out;
}
.mini-eq span:nth-child(1) { height: 4px; animation-delay: 0s; }
.mini-eq span:nth-child(2) { height: 12px; animation-delay: 0.15s; }
.mini-eq span:nth-child(3) { height: 7px; animation-delay: 0.3s; }

/* slide-up animation */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.25s var(--vf-ease), opacity 0.25s;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
