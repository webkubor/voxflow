<template>
  <transition name="slide-up">
    <div v-if="player.visible" class="global-player-bar">
      <div class="player-container">
        
        <!-- 左侧：音频元数据与光盘旋转/声波跳动 -->
        <div class="audio-info">
          <div class="cd-visualizer" :class="{ 'is-playing': isPlaying }">
            <span class="music-icon" v-if="!isPlaying">🎵</span>
            <!-- 声波均衡器跳动柱 -->
            <div class="mini-equalizer" v-else>
              <span class="eq-bar bar-1"></span>
              <span class="eq-bar bar-2"></span>
              <span class="eq-bar bar-3"></span>
              <span class="eq-bar bar-4"></span>
            </div>
          </div>
          <div class="file-details">
            <div class="filename" :title="player.filename">{{ player.filename }}</div>
            <div class="sub-text">合成产物播放器</div>
          </div>
        </div>

        <!-- 中间：自定义播放器控制中心 -->
        <div class="player-control-center">
          <!-- 播放/暂停按钮 -->
          <button class="control-btn play-pause-btn" @click="togglePlay" :title="isPlaying ? '暂停' : '播放'">
            <svg v-if="!isPlaying" class="icon-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M8 5V19L19 12L8 5Z" fill="currentColor"/>
            </svg>
            <svg v-else class="icon-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 19H10V5H6V19ZM14 5V19H18V5H14Z" fill="currentColor"/>
            </svg>
          </button>

          <!-- 进度条轨道 -->
          <div class="progress-container">
            <span class="time-label">{{ formatTime(currentTime) }}</span>
            <div 
              class="progress-slider-track" 
              ref="progressTrack"
              @mousedown="startDragProgress"
              @click="clickProgress"
            >
              <div class="progress-slider-fill" :style="{ width: progressPercent + '%' }"></div>
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
              <!-- 静音 -->
              <svg v-if="isMuted || volume === 0" class="vol-icon" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.21.05-.42.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
              </svg>
              <!-- 低音量 -->
              <svg v-else-if="volume < 0.5" class="vol-icon" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                <path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/>
              </svg>
              <!-- 高音量 -->
              <svg v-else class="vol-icon" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
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
            <n-button 
              type="primary" 
              secondary 
              size="small" 
              tag="a" 
              :href="player.url" 
              :download="player.filename"
              class="download-btn"
            >
              ⬇ 下载
            </n-button>
            <n-button 
              circle 
              quaternary 
              size="medium" 
              @click="closePlayer"
              class="close-btn"
            >
              ✕
            </n-button>
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
/**
 * 底部全局物理音频播放器 (重构苹果定制版)
 * 职责：完全隐藏原生 HTML5 控件，自定义高保真毛玻璃声波播放器
 */
import { ref, watch, nextTick, onBeforeUnmount } from 'vue';
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

// 格式化时间 00:00
const formatTime = (secs) => {
  if (isNaN(secs) || secs === Infinity) return '00:00';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

// 播放/暂停控制
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

// 音量静音切换
const toggleMute = () => {
  isMuted.value = !isMuted.value;
  if (audioPlayer.value) {
    audioPlayer.value.muted = isMuted.value;
  }
};

// 进度更新
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

// 进度条拖拽/点击逻辑
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

// 音量拖拽/点击逻辑
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

// 监听播放 URL 的变化，自动重新加载并试听
watch(
  () => player.url,
  async (newUrl) => {
    if (newUrl) {
      isPlaying.value = true;
      await nextTick();
      if (audioPlayer.value) {
        audioPlayer.value.load();
        audioPlayer.value.play().catch(() => {
          showToast('浏览器阻止了自动播放，请点击播放按钮', 'warning');
          isPlaying.value = false;
        });
      }
    }
  }
);
</script>

<style scoped>
.global-player-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 75px;
  background: rgba(12, 12, 16, 0.78) !important;
  backdrop-filter: blur(24px) saturate(160%) !important;
  -webkit-backdrop-filter: blur(24px) saturate(160%) !important;
  border-top: 1px solid rgba(255, 255, 255, 0.06) !important;
  box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.3) !important;
  z-index: 1000;
  box-sizing: border-box;
  padding: 0 20px;
}

.player-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

/* 左侧元数据 */
.audio-info {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 28%;
  min-width: 220px;
}

/* CD/声波可视化盘 */
.cd-visualizer {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(129, 140, 248, 0.15) 0%, rgba(99, 102, 241, 0.05) 100%);
  border: 1px solid rgba(129, 140, 248, 0.3);
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.cd-visualizer.is-playing {
  animation: spin-cd 6s linear infinite;
  border-color: var(--vf-primary);
  box-shadow: 0 0 15px rgba(129, 140, 248, 0.25);
}

@keyframes spin-cd {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.music-icon {
  font-size: 18px;
}

/* 极简极光声波均衡器 */
.mini-equalizer {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 16px;
}

.eq-bar {
  width: 2px;
  background: var(--vf-primary);
  border-radius: 99px;
}

.bar-1 { height: 4px; animation: bounce-bar 0.9s infinite alternate ease-in-out; }
.bar-2 { height: 12px; animation: bounce-bar 1.2s infinite alternate ease-in-out; animation-delay: 0.15s; }
.bar-3 { height: 8px; animation: bounce-bar 1s infinite alternate ease-in-out; animation-delay: 0.3s; }
.bar-4 { height: 15px; animation: bounce-bar 1.1s infinite alternate ease-in-out; animation-delay: 0.45s; }

@keyframes bounce-bar {
  from { height: 2px; }
  to { height: 16px; }
}

.file-details {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sub-text {
  font-size: 11px;
  color: var(--vf-text-3);
  margin-top: 2px;
}

/* 中间控制中心 */
.player-control-center {
  flex: 1;
  max-width: 620px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
}

/* 播放按钮 */
.control-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--vf-text-1);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  outline: none;
  transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.control-btn:hover {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  color: #fff;
  transform: scale(1.08);
  box-shadow: 0 0 12px rgba(129, 140, 248, 0.35);
}

.control-btn:active {
  transform: scale(0.95);
}

.icon-svg {
  width: 16px;
  height: 16px;
}

/* 进度条 */
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
  width: 35px;
  text-align: center;
}

.progress-slider-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  position: relative;
  cursor: pointer;
  transition: height 0.2s;
}

.progress-slider-track:hover {
  height: 6px;
}

.progress-slider-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--vf-primary) 0%, var(--vf-primary-hover) 100%);
  border-radius: 99px;
  position: absolute;
  left: 0;
  top: 0;
  box-shadow: 0 0 8px rgba(129, 140, 248, 0.4);
}

.progress-slider-thumb {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ffffff;
  border: 2px solid var(--vf-primary);
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%) scale(0);
  transition: transform 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-shadow: 0 0 8px rgba(0, 0, 0, 0.3);
}

.progress-slider-track:hover .progress-slider-thumb {
  transform: translate(-50%, -50%) scale(1.4);
}

/* 右侧面板 */
.player-right-panel {
  display: flex;
  align-items: center;
  gap: 20px;
  width: 28%;
  justify-content: flex-end;
  min-width: 220px;
}

/* 音量模块 */
.volume-container {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100px;
}

.volume-btn {
  background: none;
  border: none;
  color: var(--vf-text-2);
  cursor: pointer;
  outline: none;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s;
}

.volume-btn:hover {
  color: var(--vf-primary);
}

.vol-icon {
  width: 16px;
  height: 16px;
}

.volume-slider-track {
  flex: 1;
  height: 3px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  position: relative;
  cursor: pointer;
  transition: height 0.2s;
}

.volume-slider-track:hover {
  height: 5px;
}

.volume-slider-fill {
  height: 100%;
  background: var(--vf-text-2);
  border-radius: 99px;
  position: absolute;
  left: 0;
  top: 0;
}

.volume-slider-track:hover .volume-slider-fill {
  background: var(--vf-primary);
}

.volume-slider-thumb {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ffffff;
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%) scale(0);
  transition: transform 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.volume-slider-track:hover .volume-slider-thumb {
  transform: translate(-50%, -50%) scale(1.4);
}

/* 操作区 */
.player-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.download-btn {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}

/* 动效 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.35s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.35s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
