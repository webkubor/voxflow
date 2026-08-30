<template>
  <div class="tab-content-container">
    <!-- 头部操作区 -->
    <div class="library-header">
      <div class="header-left">
        <h3 class="tab-title">已生成音频资产</h3>
        <span class="count-pill">{{ audioFiles.length }} 条记录</span>
      </div>
      <button class="clean-btn" @click="loadAudioList">
        🔄 刷新列表
      </button>
    </div>

    <!-- 清爽精密曲目列表 (Clean Audio Table/List) -->
    <div v-if="audioFiles.length > 0" class="audio-list">
      <div 
        v-for="file in audioFiles" 
        :key="file.filename" 
        class="audio-row"
      >
        <button class="row-play-btn" @click="playAudio(file.url, file.filename)" title="试听">
          ▶
        </button>

        <div class="row-main-info">
          <span class="file-name" :title="file.filename">{{ file.filename }}</span>
          <div class="file-meta">
            <span>{{ file.created }}</span>
            <span class="meta-dot">·</span>
            <span>{{ formatBytes(file.size) }}</span>
          </div>
        </div>

        <div class="row-actions">
          <a 
            class="row-action-link" 
            :href="file.url" 
            :download="file.filename"
            title="下载文件"
          >
            下载
          </a>
          <button 
            class="row-del-btn" 
            @click="deleteAudio(file.filename)"
            title="删除"
          >
            ✕
          </button>
        </div>
      </div>
    </div>

    <!-- 暂无音频空态 -->
    <div v-else class="empty-state">
      <p>暂无已生成音频</p>
      <span>在「声音克隆」或「音色设计」页面开始合成声音</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useLibraryStore } from '../stores/library';
import { storeToRefs } from 'pinia';
import { useTasksStore } from '../stores/tasks';
import { toMessage } from '../api';

const libraryStore = useLibraryStore();
const tasksStore = useTasksStore();
const { audioFiles } = storeToRefs(libraryStore);
const { loadAudioList, playAudio, deleteAudio } = libraryStore;

// 挂载即加载 —— 之前只挂在「刷新」按钮上，进 tab 永远显示 0 条记录，
// 得手点一下刷新才有数据，看起来像文件全丢了。
onMounted(async () => {
  try {
    await loadAudioList();
  } catch (cause) {
    tasksStore.showToast(`音频列表加载失败：${await toMessage(cause)}`, 'error');
  }
});

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
  gap: 16px;
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 40px;
}

.library-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--vf-border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tab-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.count-pill {
  font-size: 11px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 2px 8px;
  border-radius: var(--vf-radius-xs);
}

.clean-btn {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 4px 12px;
  border-radius: var(--vf-radius-xs);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.clean-btn:hover { background: var(--vf-bg-hover); color: var(--vf-text-1); }

/* 清爽行列表 */
.audio-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.audio-row {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  padding: 10px 14px;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.audio-row:hover {
  background: var(--vf-bg-hover);
  border-color: var(--vf-border-strong);
}

.row-play-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-1);
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
}

.row-play-btn:hover {
  background: #ffffff;
  color: #000000;
  border-color: #ffffff;
}

.row-main-info {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--vf-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--vf-text-3);
}

.meta-dot { color: var(--vf-border-strong); }

.row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-action-link {
  font-size: 12px;
  color: var(--vf-text-2);
  text-decoration: none;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  padding: 3px 10px;
  border-radius: var(--vf-radius-xs);
  transition: all 0.15s ease;
}

.row-action-link:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
}

.row-del-btn {
  background: none;
  border: none;
  color: var(--vf-text-3);
  font-size: 12px;
  cursor: pointer;
  padding: 4px;
}
.row-del-btn:hover { color: var(--vf-err); }

.empty-state {
  text-align: center;
  padding: 60px 10px;
  color: var(--vf-text-3);
}
.empty-state p { margin: 0 0 4px 0; font-size: 14px; color: var(--vf-text-2); }
.empty-state span { font-size: 12px; }
</style>
