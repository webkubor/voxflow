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
import { computed, h, onMounted, ref } from 'vue';
import { NText } from 'naive-ui';
import { storeToRefs } from 'pinia';
import { api, toMessage } from '../api';
import { usePipelineStore } from '../stores/pipeline';
import { useTasksStore } from '../stores/tasks';
import Icon from '../components/Icon.vue';
import PlatformMark from '../components/PlatformMark.vue';

const pipelineStore = usePipelineStore();
const tasksStore = useTasksStore();
const { platforms, tracks } = storeToRefs(pipelineStore);

const accounts = ref({});
const albums = ref({});
const stageName = ref('');
const roles = ref([]);
const loading = ref(false);
const current = ref('qishui');
const openAlbum = ref('');
const linkOpen = ref(false);
const linkListingId = ref(null);
const linkTarget = ref('');
const linkSources = ref([]);
const linkBusy = ref(false);

// ── 宣推短视频 (reel-kit) 状态 ──
const promoOpen = ref(false);
const promoBusy = ref(false);
const selectedTrack = ref(null);
const promoResult = ref(null);
const promoTemplates = ref([
  { label: '🎵 音乐卡片 (music-card)', value: 'music-card' },
  { label: '📝 金句语录 (quote)', value: 'quote' },
  { label: '🎨 贴纸推广 (sticker-promo)', value: 'sticker-promo' },
]);
const promoForm = ref({
  template: 'music-card',
  per_shot: 2.8,
  // 宣推视频的封面渐变色，**是内容参数不是 UI 主题色** —— 会原样发给
  // reel-kit 合成到视频里。默认值取了品牌色，但换 UI 主题色时它不该跟着变
  // （视频配色是作品的一部分，不是界面皮肤），所以这里刻意不读 token。
  accent1: '#ec4899',
  accent2: '#6366f1',
  footer: '',
});

const openPromoModal = (row) => {
  const targetId = row.origin_id || row.id || row.track_id;
  const t = (tracks.value || []).find((x) => x.id === targetId) || {
    id: targetId,
    title: row.p?.platform_title || row.title,
    artist: stageName.value || '月栖洲',
    cover_file: row.cover_file,
  };
  selectedTrack.value = t;
  promoResult.value = null;
  promoForm.value.footer = `汽水音乐 / 抖音 搜索《${t.title || '新歌'}》全曲收听`;
  promoOpen.value = true;
};

const runGeneratePromo = async () => {
  if (!selectedTrack.value?.id) return;
  promoBusy.value = true;
  try {
    const res = await api.generatePromo({
      track_id: selectedTrack.value.id,
      template: promoForm.value.template,
      per_shot: promoForm.value.per_shot,
      accent1: promoForm.value.accent1,
      accent2: promoForm.value.accent2,
      footer: promoForm.value.footer,
    });
    if (res.ok) {
      promoResult.value = res.result;
    }
  } catch (err) {
    await tasksStore.reportError(err, { action: 'promo.generate' });
  } finally {
    promoBusy.value = false;
  }
};

const PLATFORM_STATUS = {
  preparing: '备料中',
  uploaded: '已上传',
  reviewing: '审核中',
  online: '已上架',
  published: '已上架',
  rejected: '被驳回',
};

const load = async () => {
  loading.value = true;
  try {
    // 走 api 层，不在组件里写 fetch —— 端点、错误处理、类型都在那一层
    const [acc, alb] = await Promise.all([api.platformAccounts(), api.albums()]);
    accounts.value = acc.accounts || {};
    albums.value = alb.albums || {};
    stageName.value = acc.stage_name || '';
    roles.value = acc.roles || [];
    await pipelineStore.loadPipeline();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'publish.load' });
  } finally {
    loading.value = false;
  }
};
onMounted(load);

/** 平台清单：顺序固定，不按数据多少排 —— 位置一变人就要重新找 */
const platformList = computed(() =>
  Object.entries(platforms.value || {}).map(([key, p]) => {
    const account = accounts.value[key] || null;
    const listed = tracks.value.flatMap((t) =>
      (t.listings || []).filter((l) => l.platform === key));
    const reviewing = listed.filter((l) => l.status === 'reviewing').length;
    return {
      key,
      label: p.label,
      account,
      artistName: account?.artist_name || stageName.value || '',
      songCount: listed.length,
      reviewing,
      synced: Boolean(account?.synced),
    };
  }),
);

const acc = computed(() => accounts.value[current.value] || null);

const albumsOfPlatform = computed(() =>
  Object.entries(albums.value)
    .filter(([, a]) => a.platform === current.value)
    .map(([key, a]) => ({ key, ...a }))
    .sort((a, b) => (b.publish_date || '').localeCompare(a.publish_date || '')),
);

const songsOfPlatform = computed(() =>
  tracks.value.flatMap((t) => {
    const listings = (t.listings || []).filter((l) => l.platform === current.value);
    return listings.map((p) => ({ ...t, p }));
  }).sort((a, b) => (b.p.publish_date || '').localeCompare(a.p.publish_date || '')),
);

const openLink = async (row) => {
  if (!row.p?.id) return;
  linkListingId.value = row.p.id;
  linkTarget.value = '';
  linkOpen.value = true;
  try {
    linkSources.value = (await api.sourceCandidates()).tracks || [];
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'publish.sources' });
  }
};

const confirmLink = async () => {
  if (!linkListingId.value || !linkTarget.value) return;
  linkBusy.value = true;
  try {
    await api.linkListing({ listing_id: linkListingId.value, track_id: linkTarget.value });
    linkOpen.value = false;
    await load();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'publish.link' });
  } finally {
    linkBusy.value = false;
  }
};

/**
 * 已上架列表的列。
 *
 * 定义成数据而不是写在模板里：列宽、对齐、渲染方式集中一处，
 * 加一列不用去模板里数 div。
 */
const songColumns = computed(() => [
  { title: '歌名', key: 'title', ellipsis: { tooltip: true },
    render: (r) => r.p.platform_title || r.title },
  { title: '原曲', key: 'origin', width: 168,
    render: (r) => {
      if (r.is_source) {
        const same = (r.p.platform_title || r.title) === r.title;
        return h('span', { style: 'display:inline-flex;align-items:center;gap:6px' }, [
          h('span', { style: 'font-size:12px;color:var(--vf-text-2)' }, same ? '本曲' : r.title),
          r.clip_id ? h('span', { style: 'font-size:10px;padding:1px 6px;border-radius:999px;background:var(--vf-primary-soft);color:var(--vf-primary)' }, 'Suno') : null,
        ]);
      }
      return h('button', {
        class: 'link-btn',
        onClick: (e) => { e.stopPropagation(); openLink(r); },
      }, '关联原曲');
    } },
  { title: '专辑', key: 'album', width: 170, ellipsis: { tooltip: true },
    render: (r) => r.p.album || '—' },
  { title: '状态', key: 'status', width: 80,
    render: (r) => h(NText, { depth: r.p.status === 'online' || r.p.status === 'published' ? 2 : 3 },
      () => PLATFORM_STATUS[r.p.status] || r.p.status || '—') },
  { title: '发行', key: 'date', width: 104,
    render: (r) => h(NText, { depth: 3 }, () => r.p.publish_date || '—') },
  { title: '时长', key: 'dur', width: 70, align: 'right',
    render: (r) => h(NText, { depth: 3 }, () => fmtDuration(r.p.duration)) },
  { title: '宣推', key: 'promo', width: 96, align: 'center',
    render: (r) => h('button', {
      class: 'ghost-btn',
      style: 'padding:2px 8px;font-size:11px;color:var(--vf-primary);border-color:var(--vf-primary-soft)',
      onClick: (e) => { e.stopPropagation(); openPromoModal(r); },
    }, '🎬 宣推短片') },
  { title: '', key: 'link', width: 44, align: 'right',
    render: (r) => r.p.song_url
      ? h('a', { href: r.p.song_url, target: '_blank', rel: 'noopener',
                 style: 'color:var(--vf-primary);text-decoration:none' }, '听')
      : null },
]);

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
        <h3 class="tab-title">
          <Icon name="publish" size="sm" />
          <span>平台</span>
        </h3>
        <p class="tab-subtitle">每个平台的账号、专辑与已上架作品</p>
      </div>
      <button class="ghost-btn" :disabled="loading" @click="load">
        <Icon name="refresh" size="sm" />
        <span>{{ loading ? '刷新中…' : '刷新' }}</span>
      </button>
    </div>

    <!-- 发行主体：三个平台的账号都归这个艺名，不要让人去每张卡上猜。 -->
    <div v-if="stageName" class="owner-strip">
      <span class="owner-k">发行主体</span>
      <span class="owner-name">{{ stageName }}</span>
      <span v-if="roles.length" class="owner-roles">{{ roles.join(' · ') }}</span>
    </div>

    <div class="platform-tabs">
      <button
        v-for="p in platformList"
        :key="p.key"
        class="platform-tab"
        :class="[`plat-${p.key}`, { active: current === p.key, empty: !p.songCount && !p.synced }]"
        @click="current = p.key; openAlbum = ''"
      >
        <span class="pt-top">
          <PlatformMark :platform="p.key" size="md" />
          <span class="pt-label">{{ p.label }}</span>
        </span>
        <span class="pt-artist">{{ p.artistName || '未登记账号' }}</span>
        <span class="pt-meta">
          <template v-if="p.songCount && p.reviewing === p.songCount">{{ p.reviewing }} 首审核中</template>
          <template v-else-if="p.songCount">{{ p.songCount }} 首<template v-if="p.reviewing"> · {{ p.reviewing }} 首审核中</template></template>
          <template v-else-if="p.synced">0 首在线</template>
          <template v-else>后台未同步</template>
        </span>
      </button>
    </div>

    <template v-if="acc">
      <!-- 账号卡：我是谁 + 这个平台上的数据 -->
      <n-card size="small" class="account-card">
        <n-space align="center" :size="14" :wrap="false" class="acc-head">
          <n-avatar v-if="acc.avatar_url" :src="acc.avatar_url" :size="52" round />
          <PlatformMark v-else :platform="current" size="xl" />
          <div class="acc-id">
            <div class="acc-name">
              {{ acc.artist_name || stageName || '未登记账号' }}
              <n-tag v-if="acc.stats?.roles" size="small" round :bordered="false">{{ acc.stats.roles }}</n-tag>
            </div>
            <div v-if="acc.alias?.length" class="acc-alias">{{ acc.alias.join(' · ') }}</div>
            <div class="acc-links">
              <a v-if="acc.artist_url" :href="acc.artist_url" target="_blank" rel="noopener">艺人主页</a>
              <a v-if="acc.user_url" :href="acc.user_url" target="_blank" rel="noopener">个人主页</a>
              <a v-if="acc.console_url" :href="acc.console_url" target="_blank" rel="noopener">音乐人后台</a>
            </div>
          </div>
        </n-space>

        <div v-if="acc.synced && acc.stats?.works" class="acc-stats">
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
        <p v-if="acc.synced" class="acc-synced">同步于 {{ (acc.synced_at || '').replace('T', ' ') }}</p>
        <p v-else class="acc-synced">后台数据还没同步过。身份来自艺人档案，作品数来自本地台账。</p>
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

      <!-- 这个平台上的作品。审核中也算，所以不叫「已上架」。 -->
      <section class="section">
        <h4 class="section-title">作品 <em>{{ songsOfPlatform.length }}</em></h4>
        <n-empty
          v-if="!songsOfPlatform.length"
          description="这个平台上还没有登记过作品"
          class="empty-platform"
        />
        <n-data-table
          v-else
          :columns="songColumns"
          :data="songsOfPlatform"
          :row-key="(r) => r.p.id || r.id"
          size="small"
          :bordered="false"
          max-height="440"
        />
      </section>
    </template>

    <n-modal v-model:show="linkOpen" preset="card" title="关联到原曲" style="max-width: 420px">
      <p class="modal-hint">
        平台上的歌名可以跟 Suno 原曲不同，也可以一首拆成好几条。选它对应的那首本地作品。
      </p>
      <n-select
        v-model:value="linkTarget"
        filterable
        placeholder="选一首有 Suno 或本地音频的作品"
        :options="linkSources.map((s) => ({
          value: s.id,
          label: s.suno ? `${s.title} · Suno` : s.title,
        }))"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="linkOpen = false">取消</n-button>
          <n-button type="primary" :disabled="!linkTarget" :loading="linkBusy" @click="confirmLink">
            关联
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 宣推短视频合成弹窗 (reel-kit 集成) -->
    <n-modal v-model:show="promoOpen" preset="card" title="🎬 宣推短视频工作台 (reel-kit)" style="max-width: 580px">
      <div v-if="selectedTrack" class="promo-modal-body">
        <div class="promo-track-brief">
          <img v-if="selectedTrack.cover_file" :src="'/api/cover/' + selectedTrack.id" class="promo-cover-preview" />
          <div class="promo-meta">
            <h4 class="promo-title">{{ selectedTrack.title }}</h4>
            <p class="promo-artist">演唱 / 词曲：{{ selectedTrack.artist || stageName || '月栖洲' }}</p>
            <p class="promo-hint">基于本机 reel-kit 自动化合成 1080×1920 竖版音乐卡片短片</p>
          </div>
        </div>

        <n-form label-placement="left" label-width="84" style="margin-top: 16px">
          <n-form-item label="视频模板">
            <n-select v-model:value="promoForm.template" :options="promoTemplates" />
          </n-form-item>
          <n-form-item label="每镜时长">
            <n-input-number v-model:value="promoForm.per_shot" :step="0.2" :min="1.5" :max="6.0" style="width: 100%" />
          </n-form-item>
          <n-form-item label="氛围渐变">
            <n-space>
              <n-color-picker v-model:value="promoForm.accent1" :show-alpha="false" style="width: 130px" />
              <n-color-picker v-model:value="promoForm.accent2" :show-alpha="false" style="width: 130px" />
            </n-space>
          </n-form-item>
          <n-form-item label="引导文案">
            <n-input v-model:value="promoForm.footer" placeholder="汽水音乐 / 抖音 搜索曲目全曲收听" />
          </n-form-item>
        </n-form>

        <!-- 合成结果预览 -->
        <div v-if="promoResult" class="promo-result-box">
          <div class="promo-result-header">
            <span><Icon name="check" size="sm" /> 合成成功 ({{ promoResult.duration }}s · {{ promoResult.shots_count }} 镜)</span>
            <a :href="'/api/promo/video/' + promoResult.filename" :download="promoResult.filename" class="action-link">
              ⬇ 下载视频 MP4
            </a>
          </div>
          <video controls :src="'/api/promo/video/' + promoResult.filename" class="promo-video-player" />
        </div>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="promoOpen = false">关闭</n-button>
          <n-button type="primary" :loading="promoBusy" @click="runGeneratePromo">
            {{ promoResult ? '重新生成' : '一键生成 1080×1920 短视频' }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.head {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: var(--vf-space-4);
  padding: 0 var(--vf-space-2);
}
.tab-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}
.tab-subtitle { margin: 4px 0 0; font-size: 12px; color: var(--vf-text-3); }

.owner-strip {
  display: flex; align-items: baseline; gap: var(--vf-space-3); flex-wrap: wrap;
  margin: 0 0 var(--vf-space-4);
  padding: var(--vf-space-3) var(--vf-space-4);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
}
.owner-k { font-size: 11px; color: var(--vf-text-3); letter-spacing: 0.04em; }
.owner-name { font-size: 15px; font-weight: 600; color: var(--vf-text-1); }
.owner-roles { font-size: 12px; color: var(--vf-text-2); }

.platform-tabs {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-4);
}
.platform-tab {
  padding: var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
  color: var(--vf-text-2);
  cursor: pointer;
  display: flex; flex-direction: column; gap: 4px;
  text-align: left;
  transition: border-color .15s var(--vf-ease), background .15s var(--vf-ease);
}
.platform-tab:hover { background: var(--vf-bg-3); }
.platform-tab.active { color: var(--vf-text-1); background: var(--vf-bg-3); }
.platform-tab.plat-qishui.active { border-color: var(--vf-plat-qishui); background: var(--vf-plat-qishui-soft); }
.platform-tab.plat-netease.active { border-color: var(--vf-plat-netease); background: var(--vf-plat-netease-soft); }
.platform-tab.plat-tencent.active { border-color: var(--vf-plat-tencent); background: var(--vf-plat-tencent-soft); }
.pt-top { display: flex; align-items: center; gap: var(--vf-space-2); }
.pt-label { font-size: 13px; font-weight: 600; color: var(--vf-text-1); }
.pt-artist { font-size: 12px; color: var(--vf-text-2); }
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

.origin-cell { display: inline-flex; align-items: center; gap: 6px; }
.origin-name { font-size: 12px; color: var(--vf-text-2); }
.origin-suno {
  font-size: 10px; padding: 1px 6px; border-radius: var(--vf-radius-full);
  background: var(--vf-primary-soft); color: var(--vf-primary);
}
.link-btn {
  background: none; border: 0; padding: 0; cursor: pointer;
  font-size: 12px; color: var(--vf-primary);
}
.link-btn:hover { text-decoration: underline; }
.modal-hint { margin: 0 0 var(--vf-space-4); font-size: 12px; color: var(--vf-text-3); }

/* Promo Modal styles */
.promo-modal-body {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-2);
}
.promo-track-brief {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
}
.promo-cover-preview {
  width: 64px;
  height: 64px;
  border-radius: var(--vf-radius-sm);
  object-fit: cover;
  border: 1px solid var(--vf-border);
  flex-shrink: 0;
}
.promo-meta {
  flex: 1;
  min-width: 0;
}
.promo-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.promo-artist {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--vf-text-2);
}
.promo-hint {
  margin: 3px 0 0;
  font-size: 11px;
  color: var(--vf-text-3);
}
.promo-result-box {
  margin-top: var(--vf-space-3);
  padding: var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.promo-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: var(--vf-text-1);
}
.promo-video-player {
  width: 100%;
  max-height: 380px;
  border-radius: var(--vf-radius-sm);
  background: #000;
  outline: none;
}

@media (max-width: 640px) {
  .platform-tabs { grid-template-columns: 1fr; }
}

</style>
