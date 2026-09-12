<template>
  <div class="gallery">
    <header class="g-head">
      <div>
        <h2 class="g-title"><Icon name="library" size="sm" /> 音乐卡片墙</h2>
        <p class="g-sub">
          每张卡片摆着这首歌的<strong>风格提示词</strong>和成品。横着对比就知道：
          同样是搞笑，加 <code>bassoon</code> 和加 <code>ukulele</code> 差在哪。
        </p>
      </div>
      <div class="g-actions">
        <n-switch v-model:value="onlyPrompt" size="small" />
        <span class="g-switch-label">只看有提示词的</span>
        <n-select v-model:value="srcFilter" size="small" style="width: 110px"
                  :options="[{label:'全部来源',value:''},{label:'AI 生成',value:'suno'},{label:'自制',value:'self'}]" />
        <n-button size="small" :loading="loading" @click="load">
          <Icon name="refresh" size="sm" /> 刷新
        </n-button>
        <n-button type="primary" size="small" class="glow" @click="prepOpen = true">
          <Icon name="plus" size="sm" /> 一键备料
        </n-button>
      </div>
    </header>

    <div v-if="loading && !cards.length" class="g-empty">加载中…</div>
    <div v-else-if="!shown.length" class="g-empty">还没有作品。去「AI 音乐」生成第一首。</div>

    <div v-else class="g-grid">
      <article v-for="c in shown" :key="c.id" class="card">
        <div class="card-cover">
          <img
            v-if="c.cover && !failed[c.id]" :src="c.cover" alt="" loading="lazy"
            @error="failed[c.id] = true"
          />
          <!-- 247 首里只有 43 首有封面图，所以「没有封面」是常态不是异常。
               占位要自己长得像个封面 —— 用标题首字 + 主题色渐变，
               而不是让浏览器画一个破图图标再把 alt 文字漏出来。 -->
          <div v-else class="cover-ph">
            <span class="ph-char">{{ (c.title || '?').slice(0, 1) }}</span>
          </div>
          <div class="cover-badges">
            <span class="badge-src" :class="c.source">{{ c.source_label }}</span>
            <span v-if="c.instrumental" class="badge-inst">纯音乐</span>
          </div>
        </div>

        <div class="card-body">
          <h3 class="card-title" :title="c.title">{{ c.title }}</h3>

          <!-- 卡片的主角：生成时用的提示词 -->
          <div class="card-prompt">
            <div class="prompt-head">
              <span>风格提示词</span>
              <button v-if="c.tags" class="copy-mini" @click="copy(c.tags)">复制</button>
            </div>
            <!-- 定高 + 超出滚动：提示词长短差好几倍，不定高整面卡片就参差不齐 -->
            <p v-if="c.tags" class="prompt-text">{{ c.tags }}</p>
            <p v-else class="prompt-empty">这首没记提示词（多半不是 Suno 生成的）</p>
          </div>

          <div class="card-meta">
            <span v-if="c.duration">{{ fmtDur(c.duration) }}</span>
            <span v-if="c.has_lyrics">有歌词</span>
            <span class="stage">{{ c.stage || '—' }}</span>
          </div>

          <div class="card-foot">
            <n-button v-if="c.audio" size="small" tag="a" :href="c.audio" target="_blank" rel="noopener">
              <Icon name="play" size="sm" /> 听
            </n-button>
            <n-button
              v-for="p in c.platforms" :key="p.platform"
              size="small" tag="a" :href="p.url" target="_blank" rel="noopener"
            >
              {{ p.platform }}<template v-if="p.plays"> · {{ p.plays }} 播</template>
            </n-button>
          </div>
        </div>
      </article>
    </div>
  </div>
  <PrepModal v-model:show="prepOpen" />
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import Icon from '../components/Icon.vue';
import PrepModal from '../components/PrepModal.vue';

const prepOpen = ref(false);
const failed = reactive({});   // 封面加载失败的 id，失败一次就不再重试
const cards = ref([]);
const loading = ref(false);
const onlyPrompt = ref(false);

const srcFilter = ref('');
const shown = computed(() => cards.value.filter(
  (c) => (!onlyPrompt.value || c.tags) && (!srcFilter.value || c.source === srcFilter.value),
));

const load = async () => {
  loading.value = true;
  try {
    const r = await fetch('/api/gallery?limit=60');
    const d = await r.json();
    cards.value = d.cards || [];
  } finally {
    loading.value = false;
  }
};
onMounted(load);

const fmtDur = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : '');
const copy = (t) => navigator.clipboard?.writeText(t);
</script>

<style scoped>
.gallery { padding: 4px 2px 40px; }
.g-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.g-title { display: flex; align-items: center; gap: 8px; font-size: 16px; margin: 0 0 6px; }
.g-sub { color: var(--vf-text-3); font-size: 12px; margin: 0; max-width: 620px; line-height: 1.7; }
.g-sub code { background: var(--vf-bg-3); padding: 1px 5px; border-radius: 3px; color: var(--vf-primary); }
.g-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.g-switch-label { font-size: 12px; color: var(--vf-text-3); }
.g-empty { color: var(--vf-text-3); font-size: 13px; padding: 40px 0; text-align: center; }

.g-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(268px, 1fr)); gap: 14px; }

.card {
  background: var(--vf-bg-2); border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md, 12px); overflow: hidden;
  display: flex; flex-direction: column; transition: border-color .15s, transform .15s;
}
.card:hover { border-color: var(--vf-border-strong); transform: translateY(-2px); }

.card-cover { position: relative; aspect-ratio: 1; background: var(--vf-bg-3); }
.card-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-ph {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
  background:
    radial-gradient(120% 120% at 30% 20%,
      color-mix(in srgb, var(--vf-primary) 22%, transparent), transparent 60%),
    var(--vf-bg-3);
}
.ph-char {
  font-size: 44px; font-weight: 300; line-height: 1;
  color: color-mix(in srgb, var(--vf-primary) 55%, transparent);
}
.cover-badges { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; justify-content: space-between; gap: 6px; }
.badge-src {
  font-size: 11px; padding: 2px 8px; backdrop-filter: blur(6px);
  border-radius: var(--vf-radius-full, 999px);
}
/* 自制 ≠ AI 生成。这个区分不是装饰：发行时平台会问「是否 AI 生成」，
   标错是合规问题。 */
/* 标签压在封面上，而封面亮度不可控 —— 只用半透明品牌色在亮图上会糊掉
   （实测前两张粉紫色封面上「AI 生成」被压掉一半）。所以先垫一层深色底，
   再上品牌色描边，任何封面上都读得出来。 */
.badge-src.suno {
  background: color-mix(in srgb, #000 62%, var(--vf-primary) 38%);
  color: #fff; border: 1px solid var(--vf-primary);
}
.badge-src.self {
  background: color-mix(in srgb, #000 62%, var(--vf-ok) 38%);
  color: #fff; border: 1px solid var(--vf-ok);
}
.badge-inst {
  font-size: 11px; padding: 2px 8px; backdrop-filter: blur(6px);
  border-radius: var(--vf-radius-full, 999px);
  background: color-mix(in srgb, #000 62%, var(--vf-primary) 38%);
  color: #fff; border: 1px solid var(--vf-primary);
}

.card-body { padding: 12px; display: flex; flex-direction: column; gap: 10px; flex: 1; }
.card-title { font-size: 14px; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.card-prompt { background: var(--vf-bg-3); border-radius: var(--vf-radius-sm); padding: 8px 10px; }
.prompt-head { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--vf-text-3); margin-bottom: 4px; }
.copy-mini { background: none; border: none; color: var(--vf-primary); font-size: 11px; cursor: pointer; padding: 0; }
.prompt-text {
  margin: 0; font-size: 11.5px; line-height: 1.6; color: var(--vf-text-2);
  height: 72px; overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-word;
}
.prompt-empty { margin: 0; font-size: 11.5px; color: var(--vf-text-4); height: 72px; }

.card-meta { display: flex; gap: 10px; font-size: 11px; color: var(--vf-text-3); }
.card-meta .stage { margin-left: auto; }
.card-foot { display: flex; gap: 6px; margin-top: auto; overflow-x: auto; padding-top: 2px; }
.card-foot::-webkit-scrollbar { height: 0; }
</style>
