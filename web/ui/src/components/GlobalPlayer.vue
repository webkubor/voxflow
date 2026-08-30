<template>
  <transition name="slide-up">
    <div v-if="player.visible" class="global-player-bar">
      <div class="player-container">
        
        <!-- 左侧：音频文件名与声波律动指示 -->
        <div class="audio-info">
          <div class="play-indicator" :class="{ 'is-playing': isPlaying }">
            <div v-if="isPlaying" class="cold-equalizer">
              <span class="eq-bar bar-1"></span>
              <span class="eq-bar bar-2"></span>
              <span class="eq-bar bar-3"></span>
              <span class="eq-bar bar-4"></span>
            </div>
            <span v-else class="music-note">♪</span>
          </div>
          <div class="file-details">
            <div class="filename" :title="player.filename">{{ player.filename }}</div>
            <div class="sub-text">产物试听 · 高清音频</div>
          </div>
        </div>

        <!-- 中间：精密冷光播放控制中心 -->
        <div class="player-control-center">
          <!-- 播放/暂停纯白高对比圆形按钮 -->
          <button class="play-toggle-btn" :class="{ 'is-active': isPlaying }" @click="togglePlay" :title="isPlaying ? '暂停' : '播放'">
            <svg v-if="!isPlaying" class="icon-svg" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5V19L19 12L8 5Z"/>
            </svg>
            <svg v-else class="icon-svg" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 19H10V5H6V19ZM14 5V19H18V5H14Z"/>
            </svg>
          </button>

          <!-- 极细冷光流动渐变进度条 -->
          <div class="progress-container">
            <span class="time-label">{{ formatTime(currentTime) }}</span>
            <div 
              class="progress-slider-track" 
              ref="progressTrack"
              @mousedown="startDragProgress"
              @click="clickProgress"
            >
              <div 
                class="progress-slider-fill" 
                :class="{ 'stream-active': isPlaying }"
                :style="{ width: progressPercent + '%' }"
              ></div>
              <div class="progress-slider-thumb" :style="{ left: progressPercent + '%' }"></div>
            </div>
            <span class="time-label">{{ formatTime(duration) }}</span>
          </div>
        </div>

        <!-- 右侧：音量与操作区 -->
        <div class="player-right-panel">
          <!-- 音量控制 -->
          <div class="volume-container">
            <button class="volume-btn" @click="toggleMute" :title="isMuted ? '取消静音' : '静音'">
              <svg v-if="isMuted || volume === 0" class="vol-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.21.05-.42.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
              </svg>
              <svg v-else class="vol-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L9 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
              </svg>
            </button>
            <div 
              class="volume-slider-track" 
              ref="volumeTrack"
              @mousedown="startDragVolume"
              @click="clickVolume"
            >
              <div class="volume-slider-fill" :style="{ width: (isMuted ? 0 : volume * 100) + '%' }"></div>
              <div class="volume-slider-thumb" :style="{ left: (isMuted ? 0 : volume * 100) + '%' }"></div>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="player-actions">
            <a 
              class="clean-download-link" 
              :href="player.url" 
              :download="player.filename"
            >
              下载
            </a>
            <button 
              class="clean-close-btn" 
              @click="closePlayer"
            >
              ✕
            </button>
          </div>
        </div>

        <!-- 隐藏的真实 Audio 标签 -->
        <audio 
          ref="audioPlayer" 
          :src="player.url" 
          autoplay
          @timeupdate="onTimeUpdate"
          @loadedmetadata="onLoadedMetadata"
          @ended="onEnded"
          @play="isPlaying = true"
          @pause="isPlaying = false"
        ></audio>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';
import { useLibraryStore } from '../stores/library';
import { useTasksStore } from '../stores/tasks';

const { player, closePlayer } = useLibraryStore();
const { showToast } = useTasksStore();
const audioPlayer = ref(null);

const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const progressPercent = ref(0);
const isDraggingProgress = ref(false);

const volume = ref(0.8);
const isMuted = ref(false);

const progressTrack = ref(null);
const volumeTrack = ref(null);

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
  if (audioPlayer.value) {
    audioPlayer.value.muted = isMuted.value;
  }
};

const onTimeUpdate = () => {
  if (!isDraggingProgress.value && audioPlayer.value) {
    currentTime.value = audioPlayer.value.currentTime;
    if (duration.value > 0) {
      progressPercent.value = (currentTime.value / duration.value) * 100;
    }
  }
};

const onLoadedMetadata = () => {
  if (audioPlayer.value) {
    duration.value = audioPlayer.value.duration;
  }
};

const onEnded = () => {
  isPlaying.value = false;
  currentTime.value = 0;
  progressPercent.value = 0;
};

const clickProgress = (e) => {
  if (!progressTrack.value || !audioPlayer.value || duration.value === 0) return;
  const rect = progressTrack.value.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const percent = Math.max(0, Math.min(1, clickX / rect.width));
  progressPercent.value = percent * 100;
  currentTime.value = percent * duration.value;
  audioPlayer.value.currentTime = currentTime.value;
};

const startDragProgress = (e) => {
  if (duration.value === 0) return;
  isDraggingProgress.value = true;
  handleDragProgress(e);
  
  const onMouseMove = (moveEvent) => {
    handleDragProgress(moveEvent);
  };
  
  const onMouseUp = () => {
    isDraggingProgress.value = false;
    if (audioPlayer.value) {
      audioPlayer.value.currentTime = currentTime.value;
    }
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
  };
  
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
};

const handleDragProgress = (e) => {
  if (!progressTrack.value) return;
  const rect = progressTrack.value.getBoundingClientRect();
  const dragX = e.clientX - rect.left;
  const percent = Math.max(0, Math.min(1, dragX / rect.width));
  progressPercent.value = percent * 100;
  currentTime.value = percent * duration.value;
};

const clickVolume = (e) => {
  if (!volumeTrack.value || !audioPlayer.value) return;
  const rect = volumeTrack.value.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const vol = Math.max(0, Math.min(1, clickX / rect.width));
  volume.value = vol;
  isMuted.value = false;
  audioPlayer.value.volume = vol;
  audioPlayer.value.muted = false;
};

const startDragVolume = (e) => {
  handleDragVolume(e);
  
  const onMouseMove = (moveEvent) => {
    handleDragVolume(moveEvent);
  };
  
  const onMouseUp = () => {
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
  };
  
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
};

const handleDragVolume = (e) => {
  if (!volumeTrack.value || !audioPlayer.value) return;
  const rect = volumeTrack.value.getBoundingClientRect();
  const dragX = e.clientX - rect.left;
  const vol = Math.max(0, Math.min(1, dragX / rect.width));
  volume.value = vol;
  isMuted.value = false;
  audioPlayer.value.volume = vol;
  audioPlayer.value.muted = false;
};

watch(
  () => player.url,
  async (newUrl) => {
    if (newUrl) {
      isPlaying.value = true;
      await nextTick();
      if (audioPlayer.value) {
        audioPlayer.value.load();
        audioPlayer.value.play().catch(() => {
          showToast('已加载音频，点击播放按钮试听', 'info');
          isPlaying.value = false;
        });
      }
    }
  }
);
</script>

<style scoped>
/* 终极液态毛玻璃底座 (Liquid Frosted Glass) */
.global-player-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 68px;
  background: rgba(10, 10, 14, 0.72) !important;
  backdrop-filter: blur(32px) saturate(190%) contrast(105%) !important;
  -webkit-backdrop-filter: blur(32px) saturate(190%) contrast(105%) !important;
  border-top: 1px solid rgba(255, 255, 255, 0.08) !important;
  box-shadow: 
    inset 0 1px 0 0 rgba(255, 255, 255, 0.12),
    0 -12px 32px rgba(0, 0, 0, 0.6) !important;
  z-index: 1000;
  padding: 0 24px;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.player-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
  max-width: 1240px;
  margin: 0 auto;
}

/* 左侧信息 */
.audio-info {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 26%;
  min-width: 210px;
}

.play-indicator {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s ease;
}

.play-indicator.is-playing {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(129, 140, 248, 0.4);
  box-shadow: 0 0 14px rgba(99, 102, 241, 0.25);
}

.music-note {
  font-size: 14px;
  color: var(--vf-text-2);
}

/* 冷光声波柱 */
.cold-equalizer {
  display: flex;
  align-items: flex-end;
  gap: 2.5px;
  height: 14px;
}

.eq-bar {
  width: 2px;
  background: #ffffff;
  border-radius: 99px;
  box-shadow: 0 0 6px rgba(255, 255, 255, 0.8);
}

.bar-1 { height: 4px; animation: eq-bounce 0.8s infinite alternate ease-in-out; }
.bar-2 { height: 12px; animation: eq-bounce 1.1s infinite alternate ease-in-out 0.15s; }
.bar-3 { height: 7px; animation: eq-bounce 0.9s infinite alternate ease-in-out 0.3s; }
.bar-4 { height: 14px; animation: eq-bounce 1.0s infinite alternate ease-in-out 0.45s; }

@keyframes eq-bounce {
  from { height: 3px; }
  to { height: 14px; }
}

.file-details {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  gap: 2px;
}

.filename {
  font-size: 13px;
  font-weight: 600;
  color: #ffffff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sub-text {
  font-size: 11px;
  color: var(--vf-text-3);
}

/* 中间控制中心 */
.player-control-center {
  flex: 1;
  max-width: 580px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

/* 纯白高对比按钮 + 冷光呼吸 */
.play-toggle-btn {
  background: #ffffff;
  border: none;
  color: #000000;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  outline: none;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
  transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.play-toggle-btn:hover {
  background: #f4f4f5;
  transform: scale(1.08);
  box-shadow: 0 0 16px rgba(255, 255, 255, 0.6);
}

.play-toggle-btn.is-active {
  box-shadow: 0 0 14px rgba(129, 140, 248, 0.5);
}

.icon-svg {
  width: 14px;
  height: 14px;
}

/* 进度条轨道与冷光流动动画 */
.progress-container {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.time-label {
  font-size: 11px;
  color: var(--vf-text-3);
  font-family: monospace;
  width: 34px;
  text-align: center;
}

.progress-slider-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  position: relative;
  cursor: pointer;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.5);
  transition: height 0.15s ease;
}

.progress-slider-track:hover {
  height: 6px;
}

/* 冷光流光渐变填充 */
.progress-slider-fill {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5 0%, #6366f1 35%, #a5b4fc 70%, #ffffff 100%);
  border-radius: 99px;
  position: absolute;
  left: 0;
  top: 0;
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.6), 0 0 4px rgba(255, 255, 255, 0.8);
}

.progress-slider-fill.stream-active {
  background-size: 200% 100%;
  animation: shimmer-stream 2.2s linear infinite;
}

@keyframes shimmer-stream {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

/* 冷光光环 Thumb */
.progress-slider-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ffffff;
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%) scale(0);
  box-shadow: 
    0 0 0 2px rgba(99, 102, 241, 0.5),
    0 0 10px rgba(255, 255, 255, 0.9);
  transition: transform 0.15s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.progress-slider-track:hover .progress-slider-thumb {
  transform: translate(-50%, -50%) scale(1.3);
}

/* 右侧面板 */
.player-right-panel {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 26%;
  justify-content: flex-end;
  min-width: 210px;
}

.volume-container {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 90px;
}

.volume-btn {
  background: none;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  transition: color 0.15s;
}
.volume-btn:hover { color: #ffffff; }
.vol-icon { width: 15px; height: 15px; }

.volume-slider-track {
  flex: 1;
  height: 3px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  position: relative;
  cursor: pointer;
  transition: height 0.15s;
}
.volume-slider-track:hover { height: 5px; }

.volume-slider-fill {
  height: 100%;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 99px;
}
.volume-slider-track:hover .volume-slider-fill {
  background: #ffffff;
}

.player-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.clean-download-link {
  font-size: 12px;
  font-weight: 500;
  color: #ffffff;
  text-decoration: none;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 4px 12px;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.clean-download-link:hover {
  background: #ffffff;
  color: #000000;
  border-color: #ffffff;
}

.clean-close-btn {
  background: none;
  border: none;
  color: var(--vf-text-3);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s;
}
.clean-close-btn:hover { color: #ffffff; }

.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
