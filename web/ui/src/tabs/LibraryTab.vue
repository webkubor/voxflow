<template>
  <div class="tab-content-container">
    <!-- 头部操作区 -->
    <div class="library-header">
      <h3 class="tab-title">已生成音频</h3>
      <n-button circle size="small" secondary @click="loadAudioList">
        🔄 刷新
      </n-button>
    </div>

    <!-- 历史生成音频卡片网格 -->
    <div v-if="audioFiles.length > 0" class="audio-grid-container">
      <n-grid :cols="24" :x-gap="16" :y-gap="16">
        <n-grid-item 
          v-for="file in audioFiles" 
          :key="file.filename" 
          :span="24" 
          :s="12" 
          :m="8" 
          :l="6"
        >
          <n-card class="audio-file-card" size="small" hoverable>
            <template #header>
              <div class="card-filename">
                <n-ellipsis expand-trigger="click" line-clamp="1" :tooltip="{ width: 'trigger' }">
                  {{ file.filename }}
                </n-ellipsis>
              </div>
            </template>
            
            <div class="audio-meta">
              <div class="meta-item">
                <span class="meta-label">大小:</span>
                <span class="meta-value">{{ formatBytes(file.size) }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">时间:</span>
                <span class="meta-value">{{ file.created }}</span>
              </div>
            </div>

            <template #action>
              <div class="card-actions-row">
                <n-button 
                  type="primary" 
                  size="small" 
                  secondary
                  @click="playAudio(file.url, file.filename)"
                >
                  ▶ 播放
                </n-button>
                
                <n-space size="small">
                  <n-button 
                    size="small" 
                    secondary
                    tag="a" 
                    :href="file.url" 
                    :download="file.filename"
                  >
                    ⬇ 下载
                  </n-button>
                  <n-button 
                    type="error" 
                    size="small" 
                    secondary
                    @click="deleteAudio(file.filename)"
                  >
                    🗑️ 删除
                  </n-button>
                </n-space>
              </div>
            </template>
          </n-card>
        </n-grid-item>
      </n-grid>
    </div>

    <!-- 暂无音频空态 -->
    <div v-else class="empty-library">
      <div class="empty-icon">📭</div>
      <p>暂无生成音频</p>
      <span class="empty-tip">您可以在「声音克隆」或「音色设计」页面开始合成声音。</span>
    </div>
  </div>
</template>

<script setup>
/**
 * 音频物理库选项卡
 * 职责：渲染历史生成音频物理文件，承接点击试听及物理删除与统一下载
 * API 来源：GET /api/audio-list, DELETE /api/audio/{filename}
 */
import { useLibraryStore } from '../stores/library';
import { storeToRefs } from 'pinia';

const libraryStore = useLibraryStore();
const { audioFiles } = storeToRefs(libraryStore);
const { loadAudioList, playAudio, deleteAudio } = libraryStore;

const formatBytes = (bytes) => {
  if (!bytes) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const formatTime = (timestamp) => {
  if (!timestamp) return '';
  try {
    const d = new Date(timestamp * 1000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch (e) {
    return '';
  }
};
</script>

<style scoped>
.tab-content-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.library-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.tab-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.audio-grid-container {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 20px;
}

.audio-file-card {
  background: rgba(22, 22, 26, 0.48) !important;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.04) !important;
  border-radius: 12px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.audio-file-card:hover {
  background: rgba(255, 255, 255, 0.03) !important;
  border-color: rgba(129, 140, 248, 0.3) !important;
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(129, 140, 248, 0.12) !important;
}

.card-filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.audio-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 6px;
}

.meta-item {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}

.meta-label {
  color: var(--vf-text-3);
}

.meta-value {
  color: var(--vf-text-2);
  font-weight: 500;
}

.card-actions-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.empty-library {
  text-align: center;
  padding: 80px 20px;
  color: var(--vf-text-3);
}

.empty-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.empty-library p {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-2);
}

.empty-tip {
  font-size: 12px;
  color: var(--vf-text-3);
  margin-top: 6px;
  display: inline-block;
}
</style>
