<template>
  <!-- 宣推短视频工作台（reel-kit）。
       原来这功能藏在「全网发行」页的一个弹窗里 —— 后端四个端点齐全、五个模板可用，
       界面上却只是个按钮，等于做完的能力没人找得到。独立成页：
       左边挑歌、中间调参数、下面是产出列表。 -->
  <div class="promo-tab">
    <header class="head">
      <div>
        <h2>宣推短视频</h2>
        <p class="sub">从曲库直接合成 1080×1920 竖版宣推片：音频当 BGM、歌词精选成字幕、封面当画面。</p>
      </div>
      <div class="env" :class="{ bad: env && !env.available }">
        <template v-if="env === null">检测环境中…</template>
        <template v-else-if="env.available">
          ✓ reel-kit 就绪 · {{ env.templates.length }} 个模板
        </template>
        <template v-else>✗ {{ env.error || '未检测到 reel CLI' }}</template>
      </div>
    </header>

    <div class="cols">
      <!-- 左：挑歌 -->
      <aside class="picker">
        <div class="picker-head">
          <b>选一首</b>
          <n-input v-model:value="kw" size="tiny" placeholder="搜歌名" clearable style="width: 110px" />
        </div>
        <p v-if="!candidates.length" class="empty">没有可用的歌 —— 宣推需要作品已有音频文件。</p>
        <button
          v-for="t in candidates" :key="t.id"
          class="track" :class="{ active: picked?.id === t.id }"
          @click="pick(t)"
        >
          <span class="t-title">{{ t.release_title || t.title }}</span>
          <span class="t-meta">
            {{ t.duration ? `${t.duration}s` : '' }}
            <em v-if="t.cover_file">有封面</em>
            <em v-else class="warn">无封面</em>
          </span>
        </button>
      </aside>

      <!-- 中：参数 -->
      <section class="form">
        <template v-if="!picked">
          <p class="empty-mid">左边选一首歌开始。</p>
        </template>
        <template v-else>
          <h3>{{ picked.release_title || picked.title }}</h3>

          <label class="f">
            <span>模板</span>
            <n-select v-model:value="form.template" :options="templateOptions" size="small" />
          </label>

          <label class="f">
            <span>每镜时长</span>
            <n-slider v-model:value="form.per_shot" :min="1.5" :max="6" :step="0.1" />
            <b class="num">{{ form.per_shot.toFixed(1) }}s</b>
          </label>

          <label class="f">
            <span>画面配色</span>
            <span class="colors">
              <input v-model="form.accent1" type="color" />
              <input v-model="form.accent2" type="color" />
              <small>渐变会合成进视频，跟界面主题无关</small>
            </span>
          </label>

          <label class="f col">
            <span>片尾引导语</span>
            <n-input v-model:value="form.footer" size="small" placeholder="汽水音乐 / 抖音 搜索《歌名》全曲收听" />
          </label>

          <label class="f col">
            <span>字幕<small>一行一句；留空则自动从歌词精选</small></span>
            <n-input
              v-model:value="capsText" type="textarea" size="small" :rows="4"
              placeholder="留空 = 自动从歌词里挑高潮句（纯音乐没有歌词，建议手写几句）"
            />
          </label>

          <div class="actions">
            <n-button
              type="primary" :loading="busy" :disabled="!env?.available"
              @click="run"
            >
              合成短视频
            </n-button>
            <span v-if="busy" class="hint">合成要几十秒，别重复点</span>
            <span v-else-if="!picked.cover_file" class="hint warn">这首没有封面，画面会比较素</span>
          </div>

          <p v-if="result" class="ok">
            ✓ 出片了：<code>{{ result.filename || result.path }}</code>
          </p>
        </template>
      </section>
    </div>

    <!-- 下：产出 -->
    <section class="outputs">
      <div class="out-head">
        <b>已合成 {{ videos.length }} 个</b>
        <n-button text size="tiny" @click="loadVideos">刷新</n-button>
      </div>
      <p v-if="!videos.length" class="empty">还没有合成过。</p>
      <div v-else class="grid">
        <figure v-for="v in videos" :key="v.filename">
          <video :src="`/api/promo/video/${encodeURIComponent(v.filename)}`" controls preload="metadata" />
          <figcaption>
            <span class="v-name">{{ v.filename }}</span>
            <a :href="`/api/promo/video/${encodeURIComponent(v.filename)}`" download>下载</a>
          </figcaption>
        </figure>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api } from '../api';
import { useTasksStore } from '../stores/tasks';
import type { Track } from '../types/api';

const tasksStore = useTasksStore();

type Env = { available: boolean; templates: string[]; error?: string } | null;
type Video = { filename: string; path: string; size?: number };

const env = ref<Env>(null);
const tracks = ref<Track[]>([]);
const videos = ref<Video[]>([]);
const picked = ref<Track | null>(null);
const busy = ref(false);
const kw = ref('');
const capsText = ref('');
const result = ref<{ filename?: string; path?: string } | null>(null);

// 配色是**内容参数不是界面主题** —— 会原样合成进视频，所以不读设计 token
const form = reactive({
  template: 'music-card',
  per_shot: 2.8,
  accent1: '#ec4899',
  accent2: '#6366f1',
  footer: '',
});

const TEMPLATE_LABEL: Record<string, string> = {
  'music-card': '🎵 音乐卡片',
  quote: '📝 金句语录',
  'sticker-promo': '🎨 贴纸推广',
  'sticker-square': '⬜ 贴纸方版',
  'landscape-product': '🖼 横版产品',
};

/** 模板列表来自后端实测（reel templates），不硬编码 —— 装了新模板这里自动多出来。 */
const templateOptions = computed(() =>
  (env.value?.templates || ['music-card']).map((t) => ({ label: TEMPLATE_LABEL[t] || t, value: t })));

/** 能做宣推的前提是有音频文件，没音频合不出片。 */
const candidates = computed(() => {
  const k = kw.value.trim();
  return tracks.value
    .filter((t) => t.audio_file)
    .filter((t) => !k || (t.title + (t.release_title || '')).includes(k));
});

const pick = (t: Track) => {
  picked.value = t;
  result.value = null;
  capsText.value = '';
  form.footer = `汽水音乐 / 抖音 搜索《${t.release_title || t.title}》全曲收听`;
};

const loadVideos = async () => {
  try {
    const d = await api.promoVideos();
    videos.value = (d.videos || []) as Video[];
  } catch (cause) { await tasksStore.reportError(cause, { action: 'promo.videos' }); }
};

const run = async () => {
  if (!picked.value) return;
  busy.value = true;
  result.value = null;
  try {
    const caps = capsText.value.split('\n').map((x) => x.trim()).filter(Boolean);
    const res = await api.generatePromo({
      track_id: picked.value.id,
      template: form.template,
      per_shot: form.per_shot,
      accent1: form.accent1,
      accent2: form.accent2,
      footer: form.footer,
      ...(caps.length ? { custom_caps: caps } : {}),
    });
    result.value = (res as { result?: { filename?: string; path?: string } }).result || null;
    await loadVideos();
    tasksStore.showToast('宣推短视频合成完成', 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'promo.generate' });
  } finally {
    busy.value = false;
  }
};

onMounted(async () => {
  try { env.value = (await api.promoStatus()) as Env; }
  catch { env.value = { available: false, templates: [], error: '检测失败' }; }
  try { tracks.value = (await api.pipeline()).tracks || []; } catch { /* 曲库读不到就空着 */ }
  await loadVideos();
});
</script>

<style scoped>
.promo-tab { padding: 16px 18px 40px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.head h2 { margin: 0 0 2px; font-size: 17px; }
.sub { margin: 0; font-size: 12.5px; opacity: .65; }
.env { font-size: 12px; padding: 4px 10px; border-radius: 12px; background: rgba(127,127,127,.12); flex-shrink: 0; }
.env.bad { color: #d97a7a; }

.cols { display: grid; grid-template-columns: 220px 1fr; gap: 16px; align-items: start; }
@media (max-width: 880px) { .cols { grid-template-columns: 1fr; } }

.picker { border: 1px solid rgba(127,127,127,.2); border-radius: 10px; padding: 10px; max-height: 420px; overflow-y: auto; }
.picker-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
.track {
  display: flex; flex-direction: column; gap: 2px; width: 100%; text-align: left;
  padding: 7px 9px; border-radius: 7px; border: 1px solid transparent; background: transparent;
  cursor: pointer; color: inherit; font: inherit;
}
.track:hover { background: rgba(127,127,127,.1); }
.track.active { background: rgba(127,127,127,.16); border-color: currentColor; }
.track:focus-visible { outline: 2px solid currentColor; outline-offset: 1px; }
.t-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-meta { font-size: 11px; opacity: .55; display: flex; gap: 6px; }
.t-meta em { font-style: normal; }
.t-meta .warn { color: #c98a3a; }

.form { border: 1px solid rgba(127,127,127,.2); border-radius: 10px; padding: 16px 18px; }
.form h3 { margin: 0 0 14px; font-size: 15px; }
.empty-mid { text-align: center; opacity: .5; font-size: 13px; padding: 40px 0; margin: 0; }
.f { display: grid; grid-template-columns: 84px 1fr auto; gap: 10px; align-items: center; margin-bottom: 12px; font-size: 13px; }
.f.col { grid-template-columns: 1fr; gap: 5px; }
.f > span:first-child { opacity: .7; }
.f small { display: block; font-size: 11px; opacity: .5; margin-top: 1px; }
.num { font-variant-numeric: tabular-nums; font-size: 12px; opacity: .7; }
.colors { display: flex; gap: 8px; align-items: center; }
.colors input[type=color] { width: 34px; height: 24px; border: 1px solid rgba(127,127,127,.3); border-radius: 4px; padding: 0; background: none; cursor: pointer; }
.colors small { margin: 0; }

.actions { display: flex; gap: 10px; align-items: center; margin-top: 16px; }
.hint { font-size: 12px; opacity: .6; }
.hint.warn { color: #c98a3a; }
.ok { margin: 12px 0 0; font-size: 12.5px; }
.ok code { font-size: 11.5px; }

.outputs { margin-top: 22px; border-top: 1px solid rgba(127,127,127,.15); padding-top: 14px; }
.out-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
figure { margin: 0; }
figure video { width: 100%; aspect-ratio: 9/16; object-fit: cover; border-radius: 8px; background: #000; display: block; }
figcaption { display: flex; justify-content: space-between; gap: 6px; margin-top: 4px; font-size: 11px; }
.v-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: .6; }
.empty { font-size: 12.5px; opacity: .55; margin: 6px 0; }
</style>
