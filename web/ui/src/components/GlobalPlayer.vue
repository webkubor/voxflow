<template>
  <transition name="slide-up">
    <div v-if="player.visible" class="global-player-bar">
      <div class="player-container">
        <!-- 音频信息 -->
        <div class="audio-info">
          <span class="music-icon">🎵</span>
          <div class="file-details">
            <div class="filename" :title="player.filename">{{ player.filename }}</div>
            <div class="sub-text">合成产物播放器</div>
          </div>
        </div>

        <!-- 播放器主体 -->
        <div class="player-control">
          <audio 
            ref="audioPlayer" 
            :src="player.url" 
            controls 
            autoplay
            class="native-audio"
          ></audio>
        </div>

        <!-- 操作区 -->
        <div class="player-actions">
          <n-button 
            type="primary" 
            secondary 
            size="small" 
            tag="a" 
            :href="player.url" 
            :download="player.filename"
          >
            ⬇ 下载音频
          </n-button>
          <n-button 
            circle 
            quaternary 
            size="medium" 
            @click="closePlayer"
          >
            ✕
          </n-button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
/**
 * 底部全局物理音频播放器
 * 职责：接收全局播放请求，提供一键下载，实现即时自动播
 * API 来源：直接播放来自 /api/audio/... 或静态托管路径的音频流
 */
import { ref, watch, nextTick } from 'vue';
import { useLibraryStore } from '../stores/library';
import { useTasksStore } from '../stores/tasks';

const { player, closePlayer } = useLibraryStore();
const { showToast } = useTasksStore();
const audioPlayer = ref(null);

// 监听播放 URL 的变化，自动重新加载并试听
watch(
  () => player.url,
  async (newUrl) => {
    if (newUrl) {
      await nextTick();
      if (audioPlayer.value) {
        audioPlayer.value.load();
        audioPlayer.value.play().catch(() => {
          showToast('浏览器阻止了自动播放，请点击播放器播放', 'warning');
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
  height: 70px;
  background-color: var(--vf-bg-3);
  border-top: 1px solid var(--vf-bg-4);
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.4);
  z-index: 1000;
  box-sizing: border-box;
}

.player-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
  padding: 0 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.audio-info {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 25%;
  min-width: 200px;
}

.music-icon {
  font-size: 24px;
  animation: rotate 8s linear infinite;
  display: inline-block;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.file-details {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.filename {
  font-size: 13px;
  font-weight: 500;
  color: var(--vf-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sub-text {
  font-size: 11px;
  color: var(--vf-text-3);
}

.player-control {
  flex: 1;
  display: flex;
  justify-content: center;
  max-width: 600px;
}

.native-audio {
  width: 100%;
  height: 36px;
  outline: none;
}

.player-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 25%;
  justify-content: flex-end;
  min-width: 180px;
}

/* 动效 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
