<template>
  <n-modal v-model:show="show" preset="card" class="prep-modal" title="一键备料">
    <!-- 布局刻意是**三栏并排**，不是从上往下堆。
         三样东西是并列关系（提示词 / 歌词 / 封面），谁也不是谁的下一步；
         竖着排会让人以为要按顺序做完，而且屏幕再高也不够用。 -->
    <div class="prep-top">
      <n-input
        v-model:value="theme" size="large" clearable
        placeholder="用一句话说要做什么歌，例如：上班摸鱼的搞笑歌，年轻女生唱"
        @keyup.enter="runAll"
      />
      <n-button type="primary" class="glow" :loading="busyAll" @click="runAll">
        <Icon name="suno" size="sm" /> 一键备料
      </n-button>
    </div>
    <p class="prep-hint">
      备料只花 AI 文案的钱（很少）。<strong>出封面和生成音乐要另外花积分，都得你自己点。</strong>
    </p>

    <div class="prep-cols">
      <!-- 1. 风格提示词 -->
      <section class="col">
        <header class="col-head">
          <span class="col-idx">1</span><h3>风格提示词</h3>
          <n-button size="small" :loading="busy.tags" @click="genTags">重出</n-button>
          <n-button size="small" :disabled="!tags" @click="copy(tags)">复制</n-button>
        </header>
        <div class="col-body mono" :class="{ empty: !tags }">
          {{ tags || '写乐器名和 BPM，不写情绪词 —— Suno 认 bassoon，不认「搞笑」。' }}
        </div>
      </section>

      <!-- 2. 歌词 -->
      <section class="col">
        <header class="col-head">
          <span class="col-idx">2</span><h3>歌词</h3>
          <n-button size="small" :loading="busy.lyrics" @click="genLyrics">重出</n-button>
          <n-button size="small" :disabled="!lyrics" @click="copy(lyrics)">复制</n-button>
        </header>
        <div class="col-body" :class="{ empty: !lyrics }">
          <pre v-if="lyrics">{{ lyrics }}</pre>
          <template v-else>要纯音乐（BGM）就不用管这栏，留空即可。</template>
        </div>
      </section>

      <!-- 3. 封面 -->
      <section class="col">
        <header class="col-head">
          <span class="col-idx">3</span><h3>封面</h3>
          <n-button size="small" :loading="busy.cover" @click="genCover">
            出图（花积分）
          </n-button>
        </header>
        <div class="col-body cover" :class="{ empty: !coverUrl }">
          <img v-if="coverUrl" :src="coverUrl" alt="封面" />
          <template v-else-if="busy.cover">出图中…… {{ coverStage }}（要等几十秒，别重复点，每点一次都扣积分）</template>
          <template v-else>出图会扣 museav 积分，所以要你自己点。</template>
        </div>
      </section>
    </div>

    <footer class="prep-foot">
      <span class="foot-tip">备好了就去 Suno 粘贴 —— 标题、风格标签、歌词三个框对应上面三栏。</span>
      <n-button type="primary" class="glow" tag="a" href="https://suno.com/create" target="_blank" rel="noopener">
        打开 Suno 粘贴
      </n-button>
    </footer>
  </n-modal>
</template>

<script setup>
import { reactive, ref } from 'vue';
import Icon from './Icon.vue';

const show = defineModel('show', { type: Boolean, default: false });
const theme = ref('');
const tags = ref('');
const lyrics = ref('');
const coverUrl = ref('');
const busy = reactive({ tags: false, lyrics: false, cover: false });
const coverStage = ref('');
const busyAll = ref(false);

const post = async (url, body) => {
  const r = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok || d.ok === false) throw new Error(d.error || d.detail || '失败');
  return d;
};

const genTags = async () => {
  if (!theme.value.trim()) return;
  busy.tags = true;
  try { tags.value = (await post('/api/llm/tags', { theme: theme.value })).text; }
  catch (e) { tags.value = `（失败：${e.message}）`; }
  finally { busy.tags = false; }
};

const genLyrics = async () => {
  if (!theme.value.trim()) return;
  busy.lyrics = true;
  try { lyrics.value = (await post('/api/llm/lyrics', { prompt: theme.value, style: tags.value })).text; }
  catch (e) { lyrics.value = `（失败：${e.message}）`; }
  finally { busy.lyrics = false; }
};

// 出图单独放，不进「一键」—— 它花的是 museav 积分，得由人点
// 出图是**异步任务**：接口只回 { task_id, status:'queued' }，图要等几十秒。
// 原来这里直接读 d.url / d.cover_url / d.file —— 三个字段都不存在，
// coverUrl 永远是空串，界面毫无变化，看着就像「点了没反应」。
// 而积分其实已经扣了、图也真出了，只是没人来取。所以必须轮询任务。
const genCover = async () => {
  if (!theme.value.trim()) return;
  busy.cover = true;
  coverStage.value = '提交中…';
  try {
    const d = await post('/api/cover/generate', { prompt: theme.value, title: theme.value.slice(0, 20) });
    if (!d.task_id) throw new Error('没拿到任务号');
    for (let i = 0; i < 100; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const raw = await (await fetch('/api/tasks')).json();
      const list = Array.isArray(raw) ? raw : (raw.tasks || []);
      const t = list.find((x) => x.id === d.task_id);
      if (!t) continue;
      coverStage.value = t.stage || (t.progress ? `${t.progress}%` : '出图中…');
      if (t.status === 'done') {
        const r = t.result || {};
        // cdn_url 优先；没有就走 /api/media，它只认**相对 DATA_DIR** 的路径，
        // 而任务给的是绝对路径，所以要切掉 ~/.voxflow/ 这段前缀。
        const rel = r.path ? r.path.split('/.voxflow/').pop() : '';
        coverUrl.value = r.cdn_url || (rel ? `/api/media?path=${encodeURIComponent(rel)}` : '');
        if (!coverUrl.value) throw new Error('任务完成了但没给图片地址');
        return;
      }
      if (t.status === 'error') throw new Error(t.error || '出图失败');
    }
    throw new Error('等了 5 分钟还没好，去「运营台」看任务队列');
  } catch (e) {
    coverUrl.value = '';
    alert(`出图失败：${e.message}`);
  } finally {
    busy.cover = false;
    coverStage.value = '';
  }
};

const runAll = async () => {
  if (!theme.value.trim()) return;
  busyAll.value = true;
  // 标签先出，歌词拿它当曲风参考 —— 并行的话歌词就少了这个上下文
  try { await genTags(); await genLyrics(); } finally { busyAll.value = false; }
};

const copy = (t) => navigator.clipboard?.writeText(t);
</script>

<style scoped>
.prep-modal { width: min(1100px, 94vw); }
.prep-top { display: flex; gap: 10px; }
.prep-hint { color: var(--vf-text-3); font-size: 12px; margin: 8px 0 14px; }
.prep-hint strong { color: var(--vf-warn); }

.prep-cols { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.col { border: 1px solid var(--vf-border); border-radius: var(--vf-radius-sm); overflow: hidden; display: flex; flex-direction: column; }
.col-head { display: flex; align-items: center; gap: 6px; padding: 8px 10px; background: var(--vf-bg-3); }
.col-head h3 { font-size: 13px; margin: 0; flex: 1; }
.col-idx {
  width: 18px; height: 18px; border-radius: 50%; font-size: 11px;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--vf-primary-soft); color: var(--vf-primary);
}
.col-body { padding: 10px; font-size: 12px; line-height: 1.7; height: 300px; overflow: auto; color: var(--vf-text-2); }
.col-body.empty { color: var(--vf-text-4); }
.col-body.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-word; }
.col-body pre { margin: 0; font: inherit; white-space: pre-wrap; }
.col-body.cover { display: flex; align-items: center; justify-content: center; text-align: center; }
.col-body.cover img { max-width: 100%; max-height: 280px; border-radius: var(--vf-radius-sm); }

.prep-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; }
.foot-tip { color: var(--vf-text-3); font-size: 12px; }

@media (max-width: 860px) { .prep-cols { grid-template-columns: 1fr; } }
</style>
