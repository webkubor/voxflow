<template>
  <div class="tab-content-container">
    <!-- 头部操作区 -->
    <div class="library-header">
      <div class="header-title-box">
        <span class="header-icon">📁</span>
        <h3 class="tab-title">媒体资产库</h3>
        <span class="file-count-badge">{{ audioFiles.length }} 首作品</span>
      </div>
      <button class="refresh-btn" @click="loadAudioList">
        <span>🔄 刷新曲目</span>
      </button>
    </div>

    <!-- 流媒体曲目网格 (Spotify-like Track Grid) -->
    <div v-if="audioFiles.length > 0" class="track-grid">
      <div 
        v-for="file in audioFiles" 
        :key="file.filename" 
        class="track-card"
      >
        <!-- 正方形黑胶封面区 -->
        <div class="track-cover-wrap" @click="playAudio(file.url, file.filename)">
          <div class="vinyl-record">
            <div class="vinyl-center"></div>
          </div>
          <!-- 悬浮播放按钮 -->
          <div class="hover-play-btn">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M8 5V19L19 12L8 5Z"/>
            </svg>
          </div>
        </div>

        <!-- 曲目信息 -->
        <div class="track-info">
          <span class="track-title" :title="file.filename">{{ file.filename }}</span>
          <div class="track-meta-row">
            <span class="track-date">{{ file.created }}</span>
            <span class="track-size">{{ formatBytes(file.size) }}</span>
          </div>
        </div>

        <!-- 卡片底部快捷操作 -->
        <div class="track-actions-row">
          <a 
            class="action-pill-btn download-pill" 
            :href="file.url" 
            :download="file.filename"
            title="下载音频"
          >
            ⬇ 下载
          </a>
          <button 
            class="action-pill-btn del-pill" 
            @click="deleteAudio(file.filename)"
            title="删除曲目"
          >
            🗑️
          </button>
        </div>
      </div>
    </div>

    <!-- 暂无音频空态 -->
    <div v-else class="empty-library">
      <div class="empty-disc-icon">💿</div>
      <h4>资产库空空如也</h4>
      <p>在「克隆合成」或「AI 音乐工坊」中生成你的第一首音频作品吧</p>
    </div>
  </div>
</template>

<script setup>
import { useLibraryStore } from '../stores/library';
import { storeToRefs } from 'pinia';

const libraryStore = useLibraryStore();
const { audioFiles } = storeToRefs(libraryStore);
const { loadAudioList, playAudio, deleteAudio } = libraryStore;

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};
</script>

<style scoped>
.tab-content-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 40px;
}

.library-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--vf-border-subtle);
}

.header-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon { font-size: 20px; }

.tab-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--vf-text-1);
}

.file-count-badge {
  font-size: 11px;
  font-weight: 600;
  background: rgba(129, 140, 248, 0.15);
  color: var(--vf-primary);
  padding: 3px 8px;
  border-radius: 99px;
}

.refresh-btn {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--vf-border-subtle);
  color: var(--vf-text-2);
  padding: 6px 14px;
  border-radius: 99px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--vf-text-1);
}

/* 流媒体网格 */
.track-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 18px;
}

.track-card {
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--vf-border-subtle);
  border-radius: 18px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
  position: relative;
}

.track-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
}

/* 封面与黑胶 */
.track-cover-wrap {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 12px;
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
}

.vinyl-record {
  width: 70%;
  height: 70%;
  border-radius: 50%;
  background: #09090b;
  border: 4px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.8);
}

.vinyl-center {
  width: 28%;
  height: 28%;
  border-radius: 50%;
  background: var(--vf-primary);
}

.hover-play-btn {
  position: absolute;
  bottom: 12px;
  right: 12px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--vf-primary);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  opacity: 0;
  transform: translateY(8px);
  transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.track-card:hover .hover-play-btn {
  opacity: 1;
  transform: translateY(0);
}

.hover-play-btn:hover {
  transform: scale(1.1) !important;
  background: #a5b4fc;
}

/* 曲目信息 */
.track-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.track-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--vf-text-3);
}

/* 操作行 */
.track-actions-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}

.action-pill-btn {
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 99px;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s ease;
}

.download-pill {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--vf-text-2);
}

.download-pill:hover {
  background: var(--vf-primary);
  color: #ffffff;
  border-color: var(--vf-primary);
}

.del-pill {
  background: none;
  border: none;
  color: var(--vf-text-3);
  font-size: 12px;
}

.del-pill:hover { color: var(--vf-err); }

/* 空态 */
.empty-library {
  text-align: center;
  padding: 80px 20px;
  color: var(--vf-text-3);
}

.empty-disc-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-library h4 {
  margin: 0 0 6px 0;
  font-size: 16px;
  color: var(--vf-text-2);
}

.empty-library p {
  margin: 0;
  font-size: 13px;
}
</style>
