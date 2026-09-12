<template>
  <!-- 专辑是「选歌 → 定专辑 → 发行」这条链的中间一环。
       左边列已有的辑，右边是选中那张的详情 + 把歌加进去。
       封面挂在**专辑**上（一辑一张、整辑共用），不是每首各出一张 —— 每张 1 积分。 -->
  <div class="albums-tab">
    <header class="head">
      <div>
        <h2>专辑</h2>
        <p class="sub">把挑好的歌组成一张辑：定辑名、排曲序、出一张共用封面，然后一键备料。</p>
      </div>
      <div class="head-actions">
        <n-select v-model:value="platform" :options="platformOptions" size="small" style="width: 130px" />
        <n-button type="primary" size="small" @click="showCreate = true">新建专辑</n-button>
      </div>
    </header>

    <div class="cols">
      <!-- 左：专辑列表 -->
      <aside class="list">
        <p v-if="!drafts.length" class="empty">还没有专辑。点「新建专辑」，或先去卡片墙挑歌。</p>
        <button
          v-for="a in drafts" :key="a.key"
          class="album-item" :class="{ active: a.album_id === currentId }"
          @click="currentId = a.album_id"
        >
          <span class="thumb" :class="{ none: !a.cover_local }">
            <img v-if="a.cover_local" :src="`/api/album-cover/${a.key}`" alt="" />
            <template v-else>无封面</template>
          </span>
          <span class="meta">
            <b>{{ a.title }}</b>
            <small>{{ a.track_count }} 首{{ a.publish_date ? ` · ${a.publish_date}` : '' }}</small>
          </span>
        </button>
      </aside>

      <!-- 右：详情 -->
      <section v-if="current" class="detail">
        <div class="detail-head">
          <div>
            <h3>{{ current.title }}</h3>
            <p class="sub">{{ current.description || '没写简介' }}</p>
          </div>
          <div class="detail-actions">
            <n-button size="small" :loading="busy.cover" @click="genCover">
              {{ current.cover_local ? '重出封面 ≈¥0.83' : '出封面 ≈¥0.83' }}
            </n-button>
            <n-button type="primary" size="small" :loading="busy.publish" @click="publish">一键备料发行</n-button>
          </div>
        </div>

        <div class="cover-row">
          <div class="cover" :class="{ none: !current.cover_local }">
            <img v-if="current.cover_local" :src="`/api/album-cover/${current.key}`" alt="专辑封面" />
            <template v-else>{{ busy.cover ? '出图中…… 要等几十秒，别重复点，每点一次扣 1 积分' : '还没有封面' }}</template>
          </div>
          <ol class="tracks">
            <li v-for="t in current.tracks" :key="t.id">
              <span class="no">{{ t.no ?? '-' }}</span>
              <span class="t-title">{{ t.title }}</span>
              <span class="dur">{{ t.duration ? `${t.duration}s` : '' }}</span>
              <n-button text size="tiny" @click="removeTrack(t.id)">移出</n-button>
            </li>
            <li v-if="!current.tracks.length" class="empty">这张辑还没有曲目，从下面加。</li>
          </ol>
        </div>

        <!-- 加歌 -->
        <div class="picker">
          <div class="picker-head">
            <b>加歌</b>
            <small>只列「已选定」且还没进任何专辑的 —— 一首歌同时只能在一张辑里</small>
          </div>
          <p v-if="!candidates.length" class="empty">
            没有可加的歌。去「卡片墙 · 选歌」把要发的标成「选定这首」。
          </p>
          <div v-else class="cand-grid">
            <!-- 必须显示时长：Suno 一次出两版、**同名同标签只差几秒**，
                 光看名字根本分不出选的是哪一版，选错了发出去就是另一首。 -->
            <label v-for="t in candidates" :key="t.id" class="cand">
              <input v-model="picked" type="checkbox" :value="t.id" />
              <span class="cand-title">{{ t.title }}</span>
              <span class="cand-dur">{{ t.duration ? `${t.duration}s` : '' }}</span>
            </label>
          </div>
          <n-button
            v-if="candidates.length" size="small" type="primary" ghost
            :disabled="!picked.length" :loading="busy.add" @click="addTracks"
          >
            加入专辑（{{ picked.length }}）
          </n-button>
        </div>

        <!-- 备料结果 -->
        <div v-if="steps.length" class="steps">
          <div v-for="s in steps" :key="s.step" class="step" :class="{ bad: !s.ok }">
            <span>{{ s.ok ? '✅' : '❌' }}</span>
            <b>{{ s.step }}</b>
            <span class="detail-text">{{ s.detail }}</span>
          </div>
          <p class="next">{{ nextHint }}</p>
        </div>
      </section>

      <section v-else class="detail empty-detail">
        <p>左边选一张专辑，或者新建一张。</p>
      </section>
    </div>

    <!-- 新建 -->
    <n-modal v-model:show="showCreate" preset="card" title="新建专辑" style="max-width: 440px">
      <n-form-item label="专辑名">
        <n-input v-model:value="form.title" placeholder="例如：翻车现场 · 搞笑BGM" />
      </n-form-item>
      <n-form-item label="简介（会用来生成封面）">
        <n-input v-model:value="form.description" type="textarea" :rows="2" placeholder="短视频专用喜剧配乐" />
      </n-form-item>
      <template #footer>
        <n-button type="primary" :loading="busy.create" :disabled="!form.title.trim()" @click="create">
          建这张辑
        </n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { api } from '../api';
import { useTasksStore } from '../stores/tasks';
import type { Album, Track } from '../types/api';

const tasksStore = useTasksStore();

const platform = ref('qishui');
const platformOptions = [
  { label: '汽水音乐', value: 'qishui' },
  { label: '网易云音乐', value: 'netease' },
  { label: '腾讯音乐人', value: 'tencent' },
];

const albums = ref<Album[]>([]);
const tracks = ref<Track[]>([]);
const currentId = ref('');
const picked = ref<string[]>([]);
const showCreate = ref(false);
const steps = ref<Array<{ step: string; ok: boolean; detail: string }>>([]);
const nextHint = ref('');
const busy = reactive({ create: false, add: false, cover: false, publish: false });
const form = reactive({ title: '', description: '' });

/** 只显示本地草稿辑 —— 从平台同步回来的已发行专辑不在这里改。 */
const drafts = computed(() =>
  albums.value.filter((a) => a.platform === platform.value && a.album_id.startsWith('local-')));

const current = computed(() => drafts.value.find((a) => a.album_id === currentId.value) || null);

/** 可加的歌：已选定 + 还没进任何专辑。 */
const candidates = computed(() => {
  const inAlbum = new Set(albums.value.flatMap((a) => a.tracks.map((t) => t.id)));
  return tracks.value.filter(
    (t) => ['selected', 'publishing'].includes(t.stage) && !inAlbum.has(t.id));
});

const load = async () => {
  const [a, p] = await Promise.all([api.albums(), api.pipeline()]);
  albums.value = Object.values(a.albums || {});
  tracks.value = p.tracks || [];
  if (!currentId.value && drafts.value.length) currentId.value = drafts.value[0].album_id;
};

const create = async () => {
  busy.create = true;
  try {
    const d = await api.createAlbum({
      title: form.title.trim(), platform: platform.value, description: form.description.trim(),
    });
    await load();
    currentId.value = d.album.album_id;
    showCreate.value = false;
    form.title = '';
    form.description = '';
    tasksStore.showToast(`建好了：${d.album.title}`, 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'albums.create' });
  } finally {
    busy.create = false;
  }
};

const addTracks = async () => {
  if (!current.value || !picked.value.length) return;
  busy.add = true;
  try {
    await api.albumAddTracks(current.value.album_id, {
      platform: platform.value, track_ids: [...picked.value],
    });
    picked.value = [];
    await load();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'albums.addTracks' });
  } finally {
    busy.add = false;
  }
};

const removeTrack = async (trackId: string) => {
  if (!current.value) return;
  try {
    await api.albumRemoveTrack(current.value.album_id, trackId, platform.value);
    await load();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'albums.removeTrack' });
  }
};

// 出图是异步任务，接口只回 task_id —— 必须轮询，否则界面看着像没反应，
// 而积分已经扣了、图也真出了，只是没人来取。
const waitCoverTask = async (taskId: string) => {
  for (let i = 0; i < 100; i += 1) {
    await new Promise((r) => { setTimeout(r, 3000); });
    const list = await api.tasks();
    const t = (list.tasks || []).find((x) => x.id === taskId);
    if (!t) continue;
    if (t.status === 'done') return;
    if (t.status === 'error') throw new Error(t.error || '出图失败');
  }
  throw new Error('等了 5 分钟还没好，去运营台看任务队列');
};

const genCover = async () => {
  if (!current.value) return;
  busy.cover = true;
  try {
    const d = await api.albumCover(current.value.album_id, {
      platform: platform.value, force: Boolean(current.value.cover_local),
    });
    if (d.task_id) await waitCoverTask(d.task_id);
    await load();
    tasksStore.showToast(d.skipped || '封面好了', 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'albums.cover' });
  } finally {
    busy.cover = false;
  }
};

const publish = async () => {
  if (!current.value) return;
  busy.publish = true;
  steps.value = [];
  try {
    const d = await api.albumPublish(current.value.album_id, {
      platform: platform.value, auto_cover: true, wait: true,
    });
    steps.value = d.steps || [];
    nextHint.value = d.next || '';
    await load();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'albums.publish' });
  } finally {
    busy.publish = false;
  }
};

watch(platform, () => { currentId.value = ''; picked.value = []; steps.value = []; load(); });
watch(currentId, () => { picked.value = []; steps.value = []; });
onMounted(load);
</script>

<style scoped>
.albums-tab { padding: 16px 18px 40px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.head h2 { margin: 0 0 2px; font-size: 17px; }
.sub { margin: 0; font-size: 12.5px; opacity: .65; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }

.cols { display: grid; grid-template-columns: 248px 1fr; gap: 16px; align-items: start; }
@media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }

.list { display: flex; flex-direction: column; gap: 6px; }
.album-item {
  display: flex; gap: 10px; align-items: center; text-align: left;
  padding: 8px; border-radius: 8px; border: 1px solid transparent;
  background: rgba(127, 127, 127, .06); cursor: pointer; color: inherit; font: inherit;
}
.album-item:hover { background: rgba(127, 127, 127, .12); }
.album-item.active { border-color: currentColor; background: rgba(127, 127, 127, .16); }
.album-item:focus-visible { outline: 2px solid currentColor; outline-offset: 1px; }
.thumb { width: 40px; height: 40px; border-radius: 5px; overflow: hidden; flex-shrink: 0; }
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb.none { display: grid; place-items: center; font-size: 9px; opacity: .5; background: rgba(127, 127, 127, .15); }
.meta { display: flex; flex-direction: column; min-width: 0; }
.meta b { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta small { font-size: 11px; opacity: .6; }

.detail { border: 1px solid rgba(127, 127, 127, .2); border-radius: 10px; padding: 16px; }
.empty-detail { display: grid; place-items: center; min-height: 180px; opacity: .55; font-size: 13px; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.detail-head h3 { margin: 0 0 2px; font-size: 15px; }
.detail-actions { display: flex; gap: 8px; flex-shrink: 0; }

.cover-row { display: grid; grid-template-columns: 160px 1fr; gap: 16px; margin-bottom: 18px; }
@media (max-width: 640px) { .cover-row { grid-template-columns: 1fr; } }
.cover { aspect-ratio: 1; border-radius: 8px; overflow: hidden; background: rgba(127, 127, 127, .1); }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover.none { display: grid; place-items: center; text-align: center; font-size: 11.5px; opacity: .6; padding: 10px; }

.tracks { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
.tracks li { display: flex; gap: 10px; align-items: center; padding: 6px 8px; border-radius: 6px; background: rgba(127, 127, 127, .06); font-size: 13px; }
.tracks .no { width: 18px; opacity: .5; font-variant-numeric: tabular-nums; }
.tracks .t-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tracks .dur { opacity: .5; font-size: 11.5px; font-variant-numeric: tabular-nums; }
.tracks .empty { background: none; opacity: .55; font-size: 12.5px; }

.picker { border-top: 1px solid rgba(127, 127, 127, .15); padding-top: 14px; }
.picker-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.picker-head small { font-size: 11.5px; opacity: .55; }
.cand-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 4px; margin-bottom: 10px; }
.cand { display: flex; gap: 7px; align-items: center; padding: 5px 8px; border-radius: 6px; font-size: 12.5px; cursor: pointer; }
.cand:hover { background: rgba(127, 127, 127, .1); }
.cand-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cand-dur { opacity: .5; font-size: 11px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.empty { font-size: 12.5px; opacity: .55; margin: 4px 0 10px; }

.steps { margin-top: 16px; border-top: 1px solid rgba(127, 127, 127, .15); padding-top: 12px; display: flex; flex-direction: column; gap: 5px; }
.step { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; }
.step b { flex-shrink: 0; }
.step.bad .detail-text { color: #d97a7a; }
.detail-text { opacity: .75; }
.next { margin: 6px 0 0; font-size: 12.5px; font-weight: 600; }
</style>
