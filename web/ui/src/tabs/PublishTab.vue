<script setup>
/**
 * 平台视角：切到哪个平台，就看那个平台的账号、专辑、已上架作品。
 *
 * ## 为什么改成这样
 *
 * 上一版把所有内容纵向堆在一页：三个平台的账号卡并排、云备份列表、
 * 流水线看板，从头往下摆。问题是**这些东西不在同一个维度上** ——
 * 「我的歌走到哪一步」是本地流程视角，「网易云上有哪些歌」是平台视角，
 * 混在一起看就是一堆卡片，想找什么都得从头扫一遍。
 *
 * 现在按平台切：一次只看一个平台的完整画面（我是谁 → 有多少数据 →
 * 有哪些专辑 → 有哪些歌）。流水线看板挪去「我的作品」那一屏，
 * 它属于本地流程，不属于任何平台。
 *
 * ## 界面上不放敏感信息
 *
 * 真实姓名、证件号这些在后端就被脱敏了（core/pipeline.py 的 _redact）。
 * 界面是可以给人看、可以截图演示的地方，展示的应该是作品和数据。
 */
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { usePipelineStore } from '../stores/pipeline';
import { useTasksStore } from '../stores/tasks';

const pipelineStore = usePipelineStore();
const tasksStore = useTasksStore();
const { platforms, tracks } = storeToRefs(pipelineStore);

const accounts = ref({});
const albums = ref({});
const loading = ref(false);
const current = ref('netease');   // 默认停在有数据的那个
const openAlbum = ref('');

const load = async () => {
  loading.value = true;
  try {
    const [acc, alb] = await Promise.all([
      fetch('/api/platform-accounts').then((r) => r.json()),
      fetch('/api/albums').then((r) => r.json()),
    ]);
    accounts.value = acc.accounts || {};
    albums.value = alb.albums || {};
    await pipelineStore.loadPipeline();
  } catch (cause) {
    tasksStore.showToast(cause.message || '加载平台数据失败', 'error');
  } finally {
    loading.value = false;
  }
};
onMounted(load);

/** 平台清单：顺序固定，不按数据多少排 —— 位置一变人就要重新找 */
const platformList = computed(() =>
  Object.entries(platforms.value || {}).map(([key, p]) => ({
    key,
    label: p.label,
    account: accounts.value[key] || null,
    songCount: tracks.value.filter((t) => t.platforms?.[key]).length,
  })),
);

const acc = computed(() => accounts.value[current.value] || null);

const albumsOfPlatform = computed(() =>
  Object.entries(albums.value)
    .filter(([, a]) => a.platform === current.value)
    .map(([key, a]) => ({ key, ...a }))
    .sort((a, b) => (b.publish_date || '').localeCompare(a.publish_date || '')),
);

const songsOfPlatform = computed(() =>
  tracks.value
    .filter((t) => t.platforms?.[current.value])
    .map((t) => ({ ...t, p: t.platforms[current.value] }))
    .sort((a, b) => (b.p.publish_date || '').localeCompare(a.p.publish_date || '')),
);

const fmtDuration = (sec) => {
  if (!sec) return '';
  const m = Math.floor(sec / 60);
  return `${m}:${String(sec % 60).padStart(2, '0')}`;
};
</script>

<template>
  <div class="tab-content-container">
    <div class="head">
      <div>
        <h3 class="tab-title">平台</h3>
        <p class="tab-subtitle">每个平台的账号、专辑与已上架作品</p>
      </div>
      <n-button secondary size="small" :loading="loading" @click="load">刷新</n-button>
    </div>

    <!-- 平台切换：一次只看一个平台的完整画面 -->
    <div class="platform-tabs">
      <button
        v-for="p in platformList"
        :key="p.key"
        class="platform-tab"
        :class="{ active: current === p.key, empty: !p.account }"
        @click="current = p.key"
      >
        <span class="pt-label">{{ p.label }}</span>
        <span v-if="p.account" class="pt-meta">{{ p.songCount }} 首</span>
        <span v-else class="pt-meta">未接入</span>
      </button>
    </div>

    <!-- 没接入的平台：说清楚差什么，不装作有数据 -->
    <n-empty
      v-if="!acc"
      :description="`${platformList.find(p => p.key === current)?.label || ''} 还没同步过账号数据`"
      class="empty-platform"
    >
      <template #extra>
        <p class="empty-hint">
          跑一次同步脚本就有了：<code>browser-harness &lt; scripts/sync_{{ current }}.py</code>
        </p>
      </template>
    </n-empty>

    <template v-else>
      <!-- 账号卡：我是谁 + 这个平台上的数据 -->
      <n-card size="small" class="account-card">
        <div class="acc-head">
          <img v-if="acc.avatar_url" :src="acc.avatar_url" class="acc-avatar" alt="" />
          <div class="acc-id">
            <div class="acc-name">
              {{ acc.artist_name }}
              <n-tag v-if="acc.stats?.roles" size="small" round :bordered="false">{{ acc.stats.roles }}</n-tag>
            </div>
            <div v-if="acc.alias?.length" class="acc-alias">{{ acc.alias.join(' · ') }}</div>
            <div class="acc-links">
              <a :href="acc.artist_url" target="_blank" rel="noopener">艺人主页</a>
              <a v-if="acc.user_url" :href="acc.user_url" target="_blank" rel="noopener">个人主页</a>
            </div>
          </div>
        </div>

        <div v-if="acc.stats?.works" class="acc-stats">
          <div class="stat">
            <span class="stat-n">{{ acc.stats.play_count }}</span>
            <span class="stat-l">播放量<em v-if="acc.stats.play_yesterday_delta"> +{{ acc.stats.play_yesterday_delta }}</em></span>
          </div>
          <div class="stat"><span class="stat-n">{{ acc.stats.fans }}</span><span class="stat-l">粉丝</span></div>
          <div class="stat"><span class="stat-n">{{ acc.song_count }}</span><span class="stat-l">作品</span></div>
          <div class="stat"><span class="stat-n">{{ acc.album_count }}</span><span class="stat-l">专辑</span></div>
          <div class="stat"><span class="stat-n">¥{{ acc.stats.withdrawable_cny }}</span><span class="stat-l">可提现</span></div>
          <div class="stat"><span class="stat-n">{{ acc.stats.musician_index }}</span><span class="stat-l">音乐人指数</span></div>
        </div>
        <p class="acc-synced">同步于 {{ (acc.synced_at || '').replace('T', ' ') }}</p>
      </n-card>

      <!-- 专辑：点开看曲目 -->
      <section v-if="albumsOfPlatform.length" class="section">
        <h4 class="section-title">专辑 <em>{{ albumsOfPlatform.length }}</em></h4>
        <div class="album-grid">
          <div
            v-for="a in albumsOfPlatform"
            :key="a.key"
            class="album"
            :class="{ open: openAlbum === a.key }"
            @click="openAlbum = openAlbum === a.key ? '' : a.key"
          >
            <img v-if="a.cover_api" :src="a.cover_api" class="album-cover" :alt="a.title" />
            <div v-else class="album-cover album-cover-empty">♪</div>
            <div class="album-title">{{ a.title }}</div>
            <div class="album-meta">{{ a.track_count }} 首 · {{ a.publish_date }}</div>
          </div>
        </div>

        <!-- 展开的专辑曲目 -->
        <n-card v-if="openAlbum" size="small" class="album-detail">
          <template #header>
            <span class="ad-title">{{ albums[openAlbum]?.title }}</span>
            <span class="ad-meta">{{ albums[openAlbum]?.publish_date }}</span>
          </template>
          <p v-if="albums[openAlbum]?.description" class="ad-desc">{{ albums[openAlbum].description }}</p>
          <ol class="ad-tracks">
            <li v-for="t in albums[openAlbum]?.tracks || []" :key="t.id">
              <span class="adt-name">{{ t.title }}</span>
              <span class="adt-dur">{{ fmtDuration(t.duration) }}</span>
              <a v-if="t.url" :href="t.url" target="_blank" rel="noopener" class="adt-link">听</a>
            </li>
          </ol>
        </n-card>
      </section>

      <!-- 已上架作品 -->
      <section class="section">
        <h4 class="section-title">已上架 <em>{{ songsOfPlatform.length }}</em></h4>
        <div class="song-list">
          <div v-for="s in songsOfPlatform" :key="s.id" class="song">
            <span class="song-name">{{ s.title }}</span>
            <span class="song-album">{{ s.p.album }}</span>
            <span class="song-date">{{ s.p.publish_date }}</span>
            <span class="song-dur">{{ fmtDuration(s.p.duration) }}</span>
            <a v-if="s.p.song_url" :href="s.p.song_url" target="_blank" rel="noopener" class="song-link">听</a>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.head {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: var(--vf-space-4);
}
.tab-title { margin: 0; font-size: 16px; color: var(--vf-text-1); }
.tab-subtitle { margin: 4px 0 0; font-size: 12px; color: var(--vf-text-3); }

.platform-tabs {
  display: flex; gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-4);
}
.platform-tab {
  flex: 1;
  padding: var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
  color: var(--vf-text-2);
  cursor: pointer;
  display: flex; flex-direction: column; gap: 2px;
  transition: border-color .15s, background .15s;
}
.platform-tab:hover { background: var(--vf-bg-3); }
.platform-tab.active {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
  color: var(--vf-text-1);
}
.platform-tab.empty { opacity: .55; }
.pt-label { font-size: 13px; font-weight: 600; }
.pt-meta { font-size: 11px; color: var(--vf-text-3); }

.empty-platform { padding: var(--vf-space-7) 0; }
.empty-hint { font-size: 12px; color: var(--vf-text-3); }
.empty-hint code {
  padding: 2px 6px; border-radius: var(--vf-radius-sm);
  background: var(--vf-bg-3); color: var(--vf-text-2);
}

.account-card { margin-bottom: var(--vf-space-4); }
.acc-head { display: flex; gap: var(--vf-space-3); align-items: center; }
.acc-avatar { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; }
.acc-name {
  display: flex; align-items: center; gap: var(--vf-space-2);
  font-size: 15px; font-weight: 600; color: var(--vf-text-1);
}
.acc-alias { margin-top: 2px; font-size: 12px; color: var(--vf-text-3); }
.acc-links { margin-top: var(--vf-space-1); display: flex; gap: var(--vf-space-3); }
.acc-links a { font-size: 12px; color: var(--vf-primary); text-decoration: none; }
.acc-links a:hover { text-decoration: underline; }

.acc-stats {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
  gap: var(--vf-space-2);
  margin-top: var(--vf-space-4);
}
.stat {
  padding: var(--vf-space-3) var(--vf-space-2);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-3);
  text-align: center;
}
.stat-n { display: block; font-size: 17px; font-weight: 600; color: var(--vf-primary); }
.stat-l { font-size: 11px; color: var(--vf-text-3); }
.stat-l em { font-style: normal; color: var(--vf-ok); }
.acc-synced { margin: var(--vf-space-3) 0 0; font-size: 11px; color: var(--vf-text-3); }

.section { margin-bottom: var(--vf-space-5); }
.section-title {
  margin: 0 0 var(--vf-space-3);
  font-size: 13px; color: var(--vf-text-2);
}
.section-title em { font-style: normal; color: var(--vf-text-3); }

.album-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  gap: var(--vf-space-3);
}
.album { cursor: pointer; }
.album-cover {
  width: 100%; aspect-ratio: 1;
  border-radius: var(--vf-radius-md);
  object-fit: cover;
  background: var(--vf-bg-3);
  transition: outline-color .15s;
  outline: 2px solid transparent;
}
.album.open .album-cover { outline-color: var(--vf-primary); }
.album-cover-empty {
  display: flex; align-items: center; justify-content: center;
  color: var(--vf-text-3); font-size: 26px;
}
.album-title {
  margin-top: var(--vf-space-2);
  font-size: 12px; color: var(--vf-text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.album-meta { font-size: 11px; color: var(--vf-text-3); }

.album-detail { margin-top: var(--vf-space-3); }
.ad-title { font-size: 14px; color: var(--vf-text-1); }
.ad-meta { margin-left: var(--vf-space-2); font-size: 11px; color: var(--vf-text-3); }
.ad-desc {
  margin: 0 0 var(--vf-space-3);
  font-size: 12px; line-height: 1.7; color: var(--vf-text-2);
}
.ad-tracks { margin: 0; padding-left: var(--vf-space-5); }
.ad-tracks li {
  display: flex; align-items: center; gap: var(--vf-space-3);
  padding: 3px 0; font-size: 12px; color: var(--vf-text-2);
}
.adt-name { flex: 1; }
.adt-dur { color: var(--vf-text-3); font-variant-numeric: tabular-nums; }
.adt-link { color: var(--vf-primary); text-decoration: none; }

.song-list { display: flex; flex-direction: column; }
.song {
  display: flex; align-items: center; gap: var(--vf-space-3);
  padding: var(--vf-space-2) var(--vf-space-3);
  border-bottom: 1px solid var(--vf-border);
  font-size: 12px;
}
.song:hover { background: var(--vf-bg-2); }
.song-name { flex: 1; color: var(--vf-text-1); }
.song-album { width: 150px; color: var(--vf-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.song-date { width: 84px; color: var(--vf-text-3); font-variant-numeric: tabular-nums; }
.song-dur { width: 44px; color: var(--vf-text-3); text-align: right; font-variant-numeric: tabular-nums; }
.song-link { width: 20px; color: var(--vf-primary); text-decoration: none; text-align: right; }
</style>
