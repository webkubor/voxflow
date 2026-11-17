<template>
  <div class="tab-content-container">
    <header class="page-head">
      <div>
        <h2 class="page-title">生成库</h2>
        <p class="page-sub">本机生成的所有音频，共 {{ audioFiles.length }} 条。设计样音试听满意后点「加入我的声音」，就能用来配音。</p>
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
        </select>
        <n-button @click="loadAudioList">
          <Icon name="refresh" size="sm" />
          <span>刷新</span>
        </n-button>
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
              <div class="file-name" :title="f.filename">{{ displayName(f.filename) }}</div>
              <div class="file-meta">
                <span class="meta-type" :class="guessType(f.filename)">{{ TYPE_LABEL[guessType(f.filename)] }}</span>
                <span class="meta-dot">·</span>
                <span>{{ formatBytes(f.size) }}</span>
                <span class="meta-dot">·</span>
                <span class="time-text">{{ f.created }}</span>
                <span class="meta-dot">·</span>
                <span class="raw-name">{{ f.filename }}</span>
              </div>
            </div>
            <div class="row-actions">
              <a class="action-pill" :href="f.url" :download="f.filename" title="下载">
                <Icon name="download" size="sm" />
                <span>下载</span>
              </a>
              <button v-if="guessType(f.filename) === 'design' && !f.voice" class="action-pill primary" @click="startSave(f)">加入我的声音</button>
              <span v-if="f.voice?.favorite" class="voice-link">在我的声音里 · {{ f.voice.name }}</span>
              <button v-else-if="f.voice" class="action-pill primary" @click="readdVoice(f.voice)">重新加入我的声音</button>
              <button v-if="!f.voice?.favorite" class="delete-btn" :title="'删除 ' + displayName(f.filename)" @click="removeAudio(f.filename)">
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
        <p class="empty-hint">在「我的声音」配音，或在「音色设计」生成样音，结果会出现在这里。</p>
      </template>
    </n-empty>

    <n-empty
      v-else
      :description="`没有匹配「${keyword}」的音频`"
      class="lib-empty"
    >
      <template #extra>
        <n-button @click="keyword = ''">清除搜索</n-button>
      </template>
    </n-empty>
    <n-modal v-model:show="saveDialog" preset="card" title="加入我的声音" style="width: min(480px, 92vw)">
      <p>音色名称</p>
      <n-input v-model:value="saveName" placeholder="为音色取名" />
      <p>参考音频里的原文（历史文件没有记录时必填）</p>
      <n-input v-model:value="saveText" type="textarea" placeholder="输入样音中实际说出的文字；已有记录可留空" />
      <template #footer><n-button type="primary" :loading="saving" @click="saveVoice">加入我的声音</n-button></template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useLibraryStore } from '../stores/library';
import { storeToRefs } from 'pinia';
import { useTasksStore } from '../stores/tasks';
import { api, toMessage } from '../api';
import { useVoicesStore } from '../stores/voices';
import Icon from '../components/Icon.vue';

const libraryStore = useLibraryStore();
const tasksStore = useTasksStore();
const { audioFiles } = storeToRefs(libraryStore);
const { loadAudioList, playAudio, deleteAudio } = libraryStore;

const keyword = ref('');
const filterType = ref('all');
/** 文件名去掉类型前缀、名称指纹和时间戳，只留人取的名字；原文件名仍在副行可见。 */
const displayName = (filename) => filename
  .replace(/^\[[^\]]+\]/, '')
  .replace(/(_[0-9a-f]{8})?_\d{8}_\d{6}(\.[a-z0-9]+)$/i, '')
  .replace(/\.[a-z0-9]+$/i, '') || filename;
const saveDialog = ref(false);
const saveName = ref('');
const saveText = ref('');
const saveFile = ref('');
const saving = ref(false);
const startSave = (file) => {
  saveFile.value = file.filename;
  saveName.value = displayName(file.filename);
  saveText.value = '';
  saveDialog.value = true;
};
const saveVoice = async () => {
  if (!saveName.value.trim()) return tasksStore.showToast('请填写音色名称', 'error');
  saving.value = true;
  try {
    await api.saveDesignedVoice({ filename: saveFile.value, voice_name: saveName.value.trim(), ref_text: saveText.value.trim() });
    await Promise.all([loadAudioList(), useVoicesStore().loadPersonas()]);
    saveDialog.value = false;
    tasksStore.showToast('已加入「我的声音」，可直接用于文本配音', 'success');
  } catch (error) {
    tasksStore.showToast(await toMessage(error), 'error');
  } finally { saving.value = false; }
};
// 删除规则与「我的声音」页、CLI 一致：关联声音还在「我的声音」里的文件不给删（按钮不出现）。
const removeAudio = async (filename) => {
  const voice = audioFiles.value.find((f) => f.filename === filename)?.voice;
  const lines = [`删除「${displayName(filename)}」？`, '', '· 音频文件会从本机删除，不能撤销'];
  if (voice) lines.push(`· 已移出的声音「${voice.name}」会失去这份样音`);
  if (!window.confirm(lines.join('\n'))) return;
  try { await deleteAudio(filename, true); }
  catch (error) { tasksStore.showToast(await toMessage(error), 'error'); }
};
const readdVoice = async (voice) => {
  try {
    await useVoicesStore().updatePersona(voice.key, { favorite: true });
    await loadAudioList();
    tasksStore.showToast(`「${voice.name}」已回到我的声音`, 'success');
  } catch (error) { tasksStore.showToast(await toMessage(error), 'error'); }
};

const TYPE_LABEL = {
  clone: '克隆',
  design: '设计',
  dialogue: '剧本',
  suno: '音乐',
  cover: '翻唱',
  other: '其他',
};

/**
 * 从文件名猜类型 —— 后端 audio-list 不带 type，按命名约定推断。
 *
 * ⚠️ 认的是**中文前缀**：`[克隆]`、`[设计]`、`[对话]`、`[Suno]`。
 *
 * 这里原本只匹配英文（clone / design / dialogue），而生成侧从来写的是
 * 中文方括号 —— 于是每个文件都落进「其他」，那个类型筛选框**从来没生效过**，
 * 列表里每一行的类型都显示「其他」。
 *
 * 是个静默失败：不报错、筛选框也照常能点，只是永远筛不出东西。
 * 英文分支保留着，兼容早期文件名。
 */
const guessType = (filename) => {
  const lower = filename.toLowerCase();
  if (filename.includes('[翻唱]') || lower.includes('cover')) return 'cover';
  if (filename.includes('[Suno]') || lower.includes('suno') || lower.includes('song_')) return 'suno';
  if (filename.includes('[对话]') || lower.includes('dialogue') || lower.includes('scene')) return 'dialogue';
  if (filename.includes('[设计]') || lower.includes('design')) return 'design';
  if (filename.includes('[克隆]') || lower.includes('clone')) return 'clone';
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
  font-size: var(--vf-fs-xs);
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
  font-size: var(--vf-fs-xs);
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
  font-size: var(--vf-fs-xs);
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
.meta-type.cover {
  background: linear-gradient(135deg, var(--vf-primary-soft), var(--vf-warn-soft));
  color: var(--vf-primary);
}
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

.raw-name {
  color: var(--vf-text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.action-pill.primary { color: var(--vf-primary-hover); border-color: var(--vf-primary-soft); }
.action-pill.primary:hover { border-color: var(--vf-primary); }
.voice-link { font-size: 12px; color: var(--vf-text-3); white-space: nowrap; }

/* 窄屏：操作按钮折到第二行，文件名不被挤成一个字 */
@media (max-width: 720px) {
  .audio-row { flex-wrap: wrap; }
  .row-main { flex: 1 1 calc(100% - 60px); }
  .row-actions { flex: 1 1 100%; justify-content: flex-end; flex-wrap: wrap; }
  .raw-name { display: none; }
}
</style>
