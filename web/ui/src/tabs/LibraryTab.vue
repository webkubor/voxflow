<template>
  <div class="tab-content-container">
    <header class="lib-head">
      <div class="lib-title-row">
        <h3 class="tab-title">
          <Icon name="library" size="md" />
          <span>已生成音频资产</span>
        </h3>
        <span class="count-pill">{{ audioFiles.length }} 条</span>
      </div>
      <div class="lib-tools">
        <div class="search-input-wrap">
          <Icon name="search" size="sm" class="search-icon" />
          <input
            v-model="keyword"
            type="text"
            class="search-input"
            placeholder="按文件名搜索…"
          />
          <button v-if="keyword" class="search-clear" @click="keyword = ''" title="清除">
            <Icon name="close" size="sm" />
          </button>
        </div>
        <select v-model="filterType" class="type-select" title="按类型筛选">
          <option value="all">全部类型</option>
          <option value="clone">克隆</option>
          <option value="design">设计</option>
          <option value="dialogue">剧本</option>
          <option value="suno">Suno</option>
        </select>
        <button class="ghost-btn" @click="loadAudioList">
          <Icon name="refresh" size="sm" />
          <span>刷新</span>
        </button>
      </div>
    </header>

    <div v-if="grouped.length > 0" class="lib-body">
      <section v-for="g in grouped" :key="g.label" class="group">
        <header class="group-head">
          <span class="group-label">{{ g.label }}</span>
          <span class="group-count">{{ g.files.length }} 条</span>
        </header>
        <div class="audio-list">
          <div v-for="f in g.files" :key="f.filename" class="audio-row">
            <button class="play-btn" :title="'试听 ' + f.filename" @click="playAudio(f.url, f.filename)">
              <Icon name="play" size="sm" />
            </button>
            <div class="row-main">
              <div class="file-name" :title="f.filename">{{ f.filename }}</div>
              <div class="file-meta">
                <span class="meta-type" :class="guessType(f.filename)">{{ TYPE_LABEL[guessType(f.filename)] }}</span>
                <span class="meta-dot">·</span>
                <span>{{ formatBytes(f.size) }}</span>
                <span class="meta-dot">·</span>
                <span class="time-text">{{ f.created }}</span>
              </div>
            </div>
            <div class="row-actions">
              <a class="action-pill" :href="f.url" :download="f.filename" title="下载">
                <Icon name="download" size="sm" />
                <span>下载</span>
              </a>
              <button class="delete-btn" title="删除" @click="deleteAudio(f.filename)">
                <Icon name="trash" size="sm" />
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <n-empty
      v-else-if="audioFiles.length === 0"
      description="暂无已生成音频"
      class="lib-empty"
    >
      <template #extra>
        <p class="empty-hint">在「声音克隆」或「音色设计」页面开始合成声音，产物会自动归档到这里。</p>
      </template>
    </n-empty>

    <n-empty
      v-else
      :description="`没有匹配「${keyword}」的音频`"
      class="lib-empty"
    >
      <template #extra>
        <button class="ghost-btn" @click="keyword = ''">清除搜索</button>
      </template>
    </n-empty>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useLibraryStore } from '../stores/library';
import { storeToRefs } from 'pinia';
import { useTasksStore } from '../stores/tasks';
import { toMessage } from '../api';
import Icon from '../components/Icon.vue';

const libraryStore = useLibraryStore();
const tasksStore = useTasksStore();
const { audioFiles } = storeToRefs(libraryStore);
const { loadAudioList, playAudio, deleteAudio } = libraryStore;

const keyword = ref('');
const filterType = ref('all');

const TYPE_LABEL = {
  clone: '克隆',
  design: '设计',
  dialogue: '剧本',
  suno: '音乐',
  other: '其他',
};

/** 从文件名猜类型 —— 后端 audio-list 不带 type，按命名约定推断 */
const guessType = (filename) => {
  const lower = filename.toLowerCase();
  if (lower.includes('suno') || lower.includes('song_')) return 'suno';
  if (lower.includes('dialogue') || lower.includes('scene')) return 'dialogue';
  if (lower.includes('design')) return 'design';
  if (lower.includes('clone')) return 'clone';
  return 'other';
};

const filteredFiles = computed(() => {
  const k = keyword.value.trim().toLowerCase();
  return audioFiles.value.filter((f) => {
    const t = guessType(f.filename);
    if (filterType.value !== 'all' && t !== filterType.value) return false;
    if (k && !f.filename.toLowerCase().includes(k)) return false;
    return true;
  });
});

/** 按创建日期分组：今天 / 昨天 / 本周 / 更早 */
const grouped = computed(() => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - 6);

  const buckets = {
    today: [],
    yesterday: [],
    thisWeek: [],
    earlier: [],
  };

  filteredFiles.value.forEach((f) => {
    const d = parseDate(f.created);
    if (!d) { buckets.earlier.push(f); return; }
    if (d >= today) buckets.today.push(f);
    else if (d >= yesterday) buckets.yesterday.push(f);
    else if (d >= weekStart) buckets.thisWeek.push(f);
    else buckets.earlier.push(f);
  });

  const groups = [];
  if (buckets.today.length) groups.push({ label: '今天', files: buckets.today });
  if (buckets.yesterday.length) groups.push({ label: '昨天', files: buckets.yesterday });
  if (buckets.thisWeek.length) groups.push({ label: '本周', files: buckets.thisWeek });
  if (buckets.earlier.length) groups.push({ label: '更早', files: buckets.earlier });
  return groups;
});

const parseDate = (s) => {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d) ? null : d;
};

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

onMounted(async () => {
  try {
    await loadAudioList();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'library.load' });
  }
});
</script>

<style scoped>
.tab-content-container { max-width: 1080px; margin: 0 auto; }

.tab-title { display: flex; align-items: center; gap: var(--vf-space-2); }

/* 头部 */
.lib-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--vf-space-3);
  padding-bottom: var(--vf-space-3);
  border-bottom: 1px solid var(--vf-border);
}
.lib-title-row { display: flex; align-items: center; gap: var(--vf-space-3); }
.count-pill {
  font-size: 11px;
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
}
.lib-tools { display: flex; gap: var(--vf-space-2); align-items: center; }

/* 搜索框 */
.search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 8px;
  color: var(--vf-text-3);
  pointer-events: none;
}
.search-input {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-1);
  font-size: 12px;
  padding: 6px 28px 6px 28px;
  width: 200px;
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: var(--vf-border-focus); }
.search-clear {
  position: absolute;
  right: 6px;
  background: none;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  padding: 2px;
}
.search-clear:hover { color: var(--vf-text-1); }

.type-select {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-1);
  font-size: 12px;
  padding: 6px 28px 6px 10px;
  cursor: pointer;
  outline: none;
  appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, var(--vf-text-3) 50%),
                    linear-gradient(135deg, var(--vf-text-3) 50%, transparent 50%);
  background-position: calc(100% - 14px) 50%, calc(100% - 9px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
}

/* 列表分组 */
.lib-body { display: flex; flex-direction: column; gap: var(--vf-space-5); }
.group { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.group-head {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vf-text-3);
}
.group-count {
  background: var(--vf-bg-3);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}

.audio-list { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.audio-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3) var(--vf-space-4);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  transition: border-color 0.15s, background 0.15s;
}
.audio-row:hover {
  background: var(--vf-bg-3);
  border-color: var(--vf-border-strong);
}

.play-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-1);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex: none;
  transition: all 0.15s var(--vf-ease);
}
.play-btn:hover {
  background: white;
  color: black;
  border-color: white;
  transform: scale(1.05);
}

.row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
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
  gap: var(--vf-space-2);
  font-size: 11px;
  color: var(--vf-text-3);
}
.meta-dot { color: var(--vf-border-strong); }
.meta-type {
  font-weight: 600;
  padding: 1px 6px;
  border-radius: var(--vf-radius-xs);
}
.meta-type.clone { background: var(--vf-ok-soft); color: var(--vf-ok); }
.meta-type.design { background: rgba(95, 125, 149, 0.15); color: var(--vf-info); }
.meta-type.dialogue { background: var(--vf-warn-soft); color: var(--vf-warn); }
.meta-type.suno { background: var(--vf-primary-soft); color: var(--vf-primary); }
.meta-type.other { background: var(--vf-bg-3); color: var(--vf-text-2); }

.row-actions {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}
.action-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--vf-text-2);
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  padding: 4px 10px;
  border-radius: var(--vf-radius-sm);
  text-decoration: none;
  transition: all 0.15s;
}
.action-pill:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.delete-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--vf-text-3);
  width: 28px;
  height: 28px;
  border-radius: var(--vf-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.delete-btn:hover {
  background: var(--vf-err-soft);
  color: var(--vf-err);
}

.empty-hint { font-size: 12px; color: var(--vf-text-3); margin: 0; }

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 5px 12px;
  border-radius: var(--vf-radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.ghost-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
</style>
