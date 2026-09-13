<template>
  <!-- 原创存证：把「这首歌是我设计的」变成能拿出去给人看的证据。
       左边挑歌，右边是完整留痕 + 一张可导出的证书图。
       证书图用 canvas 画，不依赖任何外部库，导出就是一张 PNG。 -->
  <div class="attest-tab">
    <header class="head">
      <div>
        <h2>原创存证</h2>
        <p class="sub">
          AI 音乐受不受著作权保护，看的是有没有<b>独创性智力投入</b> ——
          风格怎么定的、两版里挑了哪版、改过几次。这些 voxflow 一直存着，这里导成可出示的证据。
        </p>
      </div>
      <div class="head-actions">
        <n-button size="small" :disabled="!checked.length" :loading="batching" @click="makeBatch">
          批量锚定（{{ checked.length }}）
        </n-button>
      </div>
    </header>

    <div class="cols">
      <!-- 左：作品 -->
      <aside class="picker">
        <div class="picker-head">
          <n-input v-model:value="kw" size="tiny" placeholder="搜曲名" clearable />
          <n-button text size="tiny" @click="toggleAll">{{ allChecked ? '全不选' : '全选' }}</n-button>
        </div>
        <p v-if="!list.length" class="empty">曲库是空的。</p>
        <div v-for="t in list" :key="t.id" class="row" :class="{ active: cur?.track_id === t.id }">
          <input v-model="checked" type="checkbox" :value="t.id" @click.stop />
          <button class="row-btn" @click="load(t.id)">
            <span class="r-title">{{ t.release_title || t.title }}</span>
            <span class="r-meta">{{ (t.created_at || '').slice(0, 10) }}</span>
          </button>
        </div>
      </aside>

      <!-- 右：留痕 + 证书 -->
      <section class="detail">
        <p v-if="!cur" class="empty-mid">左边选一首，看它的创作留痕。</p>
        <template v-else>
          <div class="d-head">
            <div>
              <h3>{{ cur.release_title || cur.title }}</h3>
              <p class="sub">{{ cur.created_at }}　·　digest <code>{{ cur.digest.slice(0, 16) }}…</code></p>
            </div>
            <n-button size="small" type="primary" @click="exportCert">导出证书图</n-button>
          </div>

          <dl class="facts">
            <dt>风格设定</dt>
            <dd>{{ cur.design.tags || '（无）' }}</dd>
            <dt v-if="cur.design.prompt">创作提示</dt>
            <dd v-if="cur.design.prompt">{{ cur.design.prompt }}</dd>
            <dt>版本选择</dt>
            <dd>
              选用 <code>{{ (cur.generation.clip_id || '').slice(0, 8) }}</code>（{{ cur.generation.duration_sec }}s）
              <template v-if="cur.generation.alternates_not_chosen.length">
                ，弃用
                <code v-for="a in cur.generation.alternates_not_chosen" :key="a.clip_id">
                  {{ a.clip_id.slice(0, 8) }}（{{ a.duration_sec }}s）
                </code>
              </template>
              <em v-else>（无其它版本）</em>
            </dd>
            <dt>内容指纹</dt>
            <dd><code class="hash">{{ cur.content.audio_sha256 || '（音频未入库）' }}</code></dd>
            <dt>时间线</dt>
            <dd>
              <span v-if="!cur.timeline.length">（暂无事件）</span>
              <ol v-else class="tl">
                <li v-for="(e, i) in cur.timeline" :key="i">
                  <span class="tl-ts">{{ e.ts.slice(0, 16).replace('T', ' ') }}</span>
                  <span>{{ e.from ? `${e.from} → ` : '' }}{{ e.to }}</span>
                  <em v-if="e.note">{{ e.note }}</em>
                </li>
              </ol>
            </dd>
          </dl>

          <!-- 证书预览：导出的就是这张 canvas -->
          <div class="cert-wrap">
            <canvas ref="canvasEl" width="1200" height="1600" />
          </div>
        </template>
      </section>
    </div>

    <!-- 批次 -->
    <section v-if="batches.length" class="batches">
      <b>已锚定批次</b>
      <div v-for="b in batches" :key="b.file" class="batch">
        <span class="b-root"><code>{{ b.merkle_root.slice(0, 20) }}…</code></span>
        <span class="b-meta">{{ b.count }} 首 · {{ (b.built_at || '').slice(0, 16).replace('T', ' ') }}</span>
        <span class="b-titles">{{ b.titles.join('、') }}</span>
      </div>
    </section>

    <n-modal v-model:show="showAnchor" preset="card" title="链上锚定" style="max-width: 620px">
      <p class="mono-block">Merkle Root<br /><code>{{ anchor?.root }}</code></p>
      <p class="mono-block">交易 data（把它放进一笔 value=0 的自转账）<br />
        <code class="break">{{ anchor?.data_hex }}</code>
      </p>
      <p class="tip">
        签名和发送用你自己的钱包 —— <b>这里不碰私钥</b>。
        一笔交易锚定整批，L2 上 gas 通常不到一分钱。
      </p>
      <n-button size="small" @click="copy(anchor?.data_hex || '')">复制 data</n-button>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { api } from '../api';
import { useTasksStore } from '../stores/tasks';
import type { AttestDoc, Track } from '../types/api';

const tasksStore = useTasksStore();

const tracks = ref<Track[]>([]);
const cur = ref<AttestDoc | null>(null);
const checked = ref<string[]>([]);
const kw = ref('');
const batching = ref(false);
const batches = ref<Array<{ file: string; built_at: string; count: number; merkle_root: string; titles: string[] }>>([]);
const showAnchor = ref(false);
const anchor = ref<{ root: string; data_hex: string } | null>(null);
const canvasEl = ref<HTMLCanvasElement | null>(null);

const list = computed(() => {
  const k = kw.value.trim();
  return tracks.value.filter((t) => !k || (t.title + (t.release_title || '')).includes(k)).slice(0, 200);
});
const allChecked = computed(() => list.value.length > 0 && checked.value.length === list.value.length);

const toggleAll = () => {
  checked.value = allChecked.value ? [] : list.value.map((t) => t.id);
};

const load = async (id: string) => {
  try {
    cur.value = (await api.attestOne(id)).doc;
    await nextTick();
    draw();
  } catch (cause) { await tasksStore.reportError(cause, { action: 'attest.one' }); }
};

const makeBatch = async () => {
  batching.value = true;
  try {
    const r = await api.attestBatch({ track_ids: [...checked.value] });
    anchor.value = { root: r.merkle_root, data_hex: r.anchor.data_hex };
    showAnchor.value = true;
    await loadBatches();
    tasksStore.showToast(`已打包 ${r.count} 首，存证包落盘`, 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'attest.batch' });
  } finally { batching.value = false; }
};

const loadBatches = async () => {
  try { batches.value = (await api.attestBatches()).batches || []; } catch { /* 没有就空着 */ }
};

const copy = (t: string) => navigator.clipboard?.writeText(t);

/**
 * 画证书。**刻意不依赖任何图表/绘图库** —— 证书要能长期复现，
 * 少一个依赖就少一个将来画不出来的理由。
 */
const draw = () => {
  const cv = canvasEl.value;
  const d = cur.value;
  if (!cv || !d) return;
  const g = cv.getContext('2d');
  if (!g) return;
  const W = cv.width;
  const M = 90;

  g.fillStyle = '#fbfaf8';
  g.fillRect(0, 0, W, cv.height);
  g.strokeStyle = '#2b3a4a';
  g.lineWidth = 3;
  g.strokeRect(M / 2, M / 2, W - M, cv.height - M);

  let y = M + 40;
  const text = (s: string, size: number, color = '#1a1d21', weight = '400') => {
    g.fillStyle = color;
    g.font = `${weight} ${size}px -apple-system, "PingFang SC", sans-serif`;
    g.fillText(s, M, y);
    y += size * 1.55;
  };
  const wrap = (s: string, size: number, color = '#4e565f') => {
    g.fillStyle = color;
    g.font = `${size}px -apple-system, "PingFang SC", sans-serif`;
    const max = W - M * 2;
    let line = '';
    for (const ch of s) {
      if (g.measureText(line + ch).width > max) { g.fillText(line, M, y); y += size * 1.5; line = ''; }
      line += ch;
    }
    if (line) { g.fillText(line, M, y); y += size * 1.5; }
  };
  const rule = () => {
    g.strokeStyle = '#dcdfe3'; g.lineWidth = 1;
    g.beginPath(); g.moveTo(M, y); g.lineTo(W - M, y); g.stroke();
    y += 34;
  };

  text('原创存证', 26, '#3d5a73', '600');
  text(d.release_title || d.title, 52, '#1a1d21', '600');
  y += 6;
  rule();

  text('创作时间', 22, '#79828d');
  text(d.created_at.replace('T', ' '), 28);
  y += 8;

  text('风格设定（独创性投入）', 22, '#79828d');
  wrap(d.design.tags || '（无）', 26);
  y += 8;

  if (d.design.prompt) {
    text('创作提示', 22, '#79828d');
    wrap(d.design.prompt, 26);
    y += 8;
  }

  text('版本选择', 22, '#79828d');
  wrap(
    `选用 ${(d.generation.clip_id || '').slice(0, 12)}（${d.generation.duration_sec ?? '?'}s）`
    + (d.generation.alternates_not_chosen.length
      ? `；同批弃用 ${d.generation.alternates_not_chosen.map((a) => `${a.clip_id.slice(0, 12)}(${a.duration_sec}s)`).join('、')}`
      : '；无其它版本'),
    26,
  );
  y += 8;
  rule();

  text('音频内容指纹 SHA-256', 22, '#79828d');
  g.font = '22px ui-monospace, Menlo, monospace';
  g.fillStyle = '#1a1d21';
  const h = d.content.audio_sha256 || '（音频未入库）';
  g.fillText(h.slice(0, 32), M, y); y += 32;
  g.fillText(h.slice(32), M, y); y += 44;

  text('留痕摘要 digest', 22, '#79828d');
  g.font = '22px ui-monospace, Menlo, monospace';
  g.fillStyle = '#1a1d21';
  g.fillText(d.digest.slice(0, 32), M, y); y += 32;
  g.fillText(d.digest.slice(32), M, y); y += 44;

  rule();
  text(`时间线共 ${d.timeline.length} 条事件`, 22, '#79828d');
  d.timeline.slice(0, 6).forEach((e) => {
    wrap(`${e.ts.slice(0, 16).replace('T', ' ')}　${e.from ? `${e.from} → ` : ''}${e.to}${e.note ? `　${e.note}` : ''}`, 22);
  });

  // 页脚
  g.fillStyle = '#79828d';
  g.font = '20px -apple-system, "PingFang SC", sans-serif';
  g.fillText(`VoxFlow 声流 · ${d.schema} · 导出于 ${new Date().toLocaleString('zh-CN')}`,
    M, cv.height - M - 10);
};

const exportCert = () => {
  const cv = canvasEl.value;
  const d = cur.value;
  if (!cv || !d) return;
  const a = document.createElement('a');
  a.download = `原创存证-${d.release_title || d.title}-${d.digest.slice(0, 8)}.png`;
  a.href = cv.toDataURL('image/png');
  a.click();
};

watch(cur, () => nextTick(draw));
onMounted(async () => {
  try { tracks.value = (await api.pipeline()).tracks || []; } catch { /* 空着 */ }
  await loadBatches();
});
</script>

<style scoped>
.attest-tab { padding: 16px 18px 40px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.head h2 { margin: 0 0 3px; font-size: 17px; }
.sub { margin: 0; font-size: 12.5px; opacity: .65; max-width: 640px; }
.head-actions { flex-shrink: 0; }

.cols { display: grid; grid-template-columns: 230px 1fr; gap: 16px; align-items: start; }
@media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }

.picker { border: 1px solid rgba(127,127,127,.2); border-radius: 10px; padding: 10px; max-height: 520px; overflow-y: auto; }
.picker-head { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.row { display: flex; gap: 7px; align-items: center; padding: 3px 4px; border-radius: 6px; }
.row.active { background: rgba(127,127,127,.14); }
.row:hover { background: rgba(127,127,127,.08); }
.row-btn { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; text-align: left;
  background: none; border: none; cursor: pointer; color: inherit; font: inherit; padding: 3px 2px; }
.r-title { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.r-meta { font-size: 10.5px; opacity: .5; }

.detail { border: 1px solid rgba(127,127,127,.2); border-radius: 10px; padding: 16px 18px; }
.empty-mid { text-align: center; opacity: .5; font-size: 13px; padding: 50px 0; margin: 0; }
.d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.d-head h3 { margin: 0 0 2px; font-size: 15px; }

.facts { margin: 0 0 18px; display: grid; grid-template-columns: 84px 1fr; gap: 6px 12px; font-size: 13px; }
.facts dt { opacity: .6; }
.facts dd { margin: 0; word-break: break-word; }
.facts code { font-size: 11.5px; background: rgba(127,127,127,.12); padding: 1px 5px; border-radius: 3px; margin-right: 4px; }
.facts .hash { font-size: 11px; word-break: break-all; }
.facts em { font-style: normal; opacity: .5; }
.tl { margin: 0; padding-left: 16px; }
.tl li { margin-bottom: 3px; font-size: 12px; }
.tl-ts { opacity: .55; margin-right: 8px; font-variant-numeric: tabular-nums; }
.tl em { font-style: normal; opacity: .6; margin-left: 6px; }

.cert-wrap { border-top: 1px solid rgba(127,127,127,.15); padding-top: 14px; }
.cert-wrap canvas { width: 100%; max-width: 460px; height: auto; border: 1px solid rgba(127,127,127,.2); border-radius: 6px; display: block; }

.batches { margin-top: 20px; border-top: 1px solid rgba(127,127,127,.15); padding-top: 12px; }
.batch { display: flex; gap: 12px; align-items: baseline; font-size: 12px; padding: 4px 0; }
.b-root code { font-size: 11px; }
.b-meta { opacity: .6; white-space: nowrap; }
.b-titles { opacity: .5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.mono-block { font-size: 12.5px; margin: 0 0 12px; }
.mono-block code { font-size: 11.5px; }
.break { word-break: break-all; }
.tip { font-size: 12px; opacity: .7; margin: 0 0 12px; }
.empty { font-size: 12.5px; opacity: .55; }
</style>
