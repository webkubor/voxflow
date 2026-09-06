<template>
  <div class="board-wrap">
    <header class="board-head">
      <h3 class="board-title">
        <Icon name="board" size="md" />
        <span>发歌记录</span>
      </h3>
      <div class="board-tools">
        <!-- 出封面的比例。放在顶栏而不是每一行：封面绝大多数是方图，
             逐行放选择器会让操作区变重，而这个选择改一次就够用一批。
             不限于下拉里的几个 —— 可以直接输入任意 W:H（如 1:2.1）。 -->
        <label class="ratio-pick" :title="`出封面用的画幅。可直接输入任意 W:H，合法性由中台判定`">
          <span class="ratio-label">封面比例</span>
          <input
            v-model="coverRatio"
            class="ratio-input"
            list="cover-ratios"
            placeholder="1:1"
            spellcheck="false"
          />
          <datalist id="cover-ratios">
            <option v-for="r in coverCaps.common_ratios || []" :key="r.value" :value="r.value">
              {{ r.label }}
            </option>
          </datalist>
          <!-- 直接把「会拿到多大的图」写出来。平台对封面有硬性尺寸要求
               （汽水 ≥1440、网易云 ≥1400），光给个比例人判断不了够不够。 -->
          <span v-if="coverSize" class="ratio-size">→ {{ coverSize }}</span>
        </label>
        <button class="ghost-btn" @click="openInbox">
          <Icon name="upload" size="sm" />
          <span>从下载导入</span>
        </button>
        <button class="ghost-btn" @click="load">
          <Icon name="refresh" size="sm" />
          <span>刷新</span>
        </button>
      </div>
    </header>

    <!-- 计数条 -->
    <div class="counters">
      <div v-for="c in counters" :key="c.key" class="counter" :class="{ 'is-zero': !c.n, 'is-current': c.key === currentStageKey }">
        <span class="counter-n">{{ c.n }}</span>
        <span class="counter-label">{{ c.label }}</span>
      </div>
    </div>

    <n-alert v-if="error" type="error" :show-icon="false" class="board-err">{{ error }}</n-alert>

    <n-empty
      v-if="!tracks.length"
      description="还没有作品"
      class="board-empty"
    >
      <template #extra>
        <p class="empty-hint">去「AI 音乐」出一首，会自动登记到这里。</p>
        <button class="ghost-btn" @click="openInbox">
          <Icon name="upload" size="sm" />
          <span>或从下载目录导入</span>
        </button>
      </template>
    </n-empty>

    <div v-else class="track-list">
      <!-- 批量工具条 -->
      <div v-if="selectedIds.size" class="batch-bar">
        <span class="batch-count">已选 {{ selectedIds.size }} 首</span>
        <button class="ghost-btn small" @click="selectedIds = new Set()">取消选择</button>
        <button class="primary-btn small" :disabled="batchBusy" @click="batchAdvance">
          {{ batchBusy ? '推进中…' : '批量推进到下一步' }}
        </button>
        <span class="batch-hint">发版那步（selected → publishing）需单独选平台</span>
      </div>

      <article v-for="t in tracks" :key="t.id" class="track">
        <div class="track-head">
          <!-- 批量勾选 -->
          <label v-if="canBatchAdvance(t)" class="track-check" :title="`勾选「${t.title}」`">
            <input
              type="checkbox"
              :checked="selectedIds.has(t.id)"
              @change="toggleSelect(t.id)"
            />
          </label>
          <div v-else class="track-check-spacer"></div>

          <!-- 封面 -->
          <img v-if="t.cover_url" :src="t.cover_url" class="track-cover" :alt="t.title" />
          <div v-else class="track-cover track-cover-empty">♪</div>

          <div class="track-main">
            <div class="track-title-row">
              <span class="track-title">{{ t.title }}</span>
              <span class="stage-pill" :class="`stage-${t.stage}`">{{ t.stage_label }}</span>
            </div>
            <p v-if="t.clip_id || t.release_title" class="track-id-row">
              <span v-if="t.clip_id" class="meta-pill">Suno {{ t.clip_id.slice(0, 8) }}</span>
              <span v-if="t.release_title" class="meta-pill">发行 {{ t.release_title }}</span>
              <span v-if="t.release_platform" class="meta-pill">
                <PlatformMark :platform="t.release_platform" size="sm" />
                {{ platformLabel(t.release_platform) }} · 独家
              </span>
            </p>
            <p v-if="t.album_desc" class="track-desc">{{ t.album_desc }}</p>

            <!-- n-steps 进度：圆点 + 文字 label，比纯圆点好懂 -->
            <div class="steps">
              <template v-for="(s, i) in stages" :key="s">
                <div class="step" :class="stepClass(t.stage, s, i)">
                  <span class="step-dot">
                    <Icon v-if="i < stageIndex(t.stage)" name="check" size="sm" />
                  </span>
                  <span class="step-label">{{ stageLabels[s] }}</span>
                </div>
                <div v-if="i < stages.length - 1" class="step-line" :class="{ done: i < stageIndex(t.stage) }"></div>
              </template>
            </div>

            <audio v-if="t.audio_url" :src="t.audio_url" controls preload="none" class="track-audio" />
          </div>
        </div>

        <div v-if="coverJob(t.id)" class="track-progress">
          <div class="track-progress-bar">
            <div
              class="track-progress-fill"
              :style="{ width: (Number(coverJob(t.id).progress) || 8) + '%' }"
            />
          </div>
          <span class="track-progress-label">
            {{ coverJob(t.id).stage || '处理中' }}
            {{ Number.isFinite(Number(coverJob(t.id).progress)) ? `${Math.round(coverJob(t.id).progress)}%` : '' }}
          </span>
        </div>

        <div class="track-foot">
          <div class="track-tags">
            <span v-if="t.voice" class="meta-pill"><Icon name="voice" size="sm" />{{ t.voice }}</span>
            <span
              v-for="(info, pk) in t.platforms"
              :key="pk"
              class="meta-pill warn"
            >
              <PlatformMark :platform="pk" size="sm" />
              {{ platformLabel(pk) }} · {{ statusLabel(info.status) }}
              <span v-if="waitedDays(info) !== null"
                    :class="['wait-badge', { overdue: waitedDays(info) > 3 }]">
                已等 {{ waitedDays(info) }} 天
              </span>
            </span>
          </div>
          <div class="track-actions">
            <!-- 只在**缺封面**时出现：已经有封面的曲目再放一个出图按钮，
                 唯一的作用就是让人误点、白烧 2 积分。 -->
            <button
              v-if="!t.cover_url"
              class="ghost-btn small"
              :disabled="!coverCaps.can_generate || !!coverJob(t.id)"
              :title="coverCaps.detail"
              @click="genCover(t)"
            >
              <Icon name="sparkles" size="sm" />
              <span>{{ coverJob(t.id) ? '出图中…' : coverBtnLabel }}</span>
            </button>
            <button
              v-else
              class="ghost-btn small"
              :disabled="!!coverJob(t.id)"
              title="本地 GPU 超分到 1440，不花中台积分"
              @click="upscaleCover(t)"
            >
              <Icon name="sparkles" size="sm" />
              <span>{{ coverJob(t.id)?.type === 'cover_upscale' ? '超分中…' : '超分封面' }}</span>
            </button>
            <button
              v-if="t.lyrics || Object.keys(t.platforms || {}).length"
              class="ghost-btn small"
              @click="toggleExpand(t.id)"
            >
              <Icon :name="expanded.has(t.id) ? 'chevron-up' : 'chevron-down'" size="sm" />
              <span>{{ expanded.has(t.id) ? '收起' : '详情' }}</span>
            </button>
            <button
              v-if="nextAction(t)"
              class="primary-btn small"
              :class="`action-${nextAction(t).type}`"
              :disabled="busyId === t.id"
              @click="advance(t)"
            >
              <Icon name="arrow-right" size="sm" />
              <span>{{ nextAction(t).label }}</span>
            </button>
          </div>
        </div>

        <!-- 详情：试听来源 / 备料清单 / 歌词 / 发布配置 -->
        <div v-if="expanded.has(t.id)" class="track-detail">
          <!-- 三个来源各有各的用处，所以并列摆出来，不用去别处找 -->
          <div class="detail-block">
            <span class="detail-label">试听与来源</span>
            <!-- ⚠️ .detail-block 是横向 flex（56px 标签 + 内容），
                 内容必须包在**一个**容器里 —— 直接塞多个兄弟节点的话，
                 它们会各自成为并排的 flex 子项，被挤成竖排文字。 -->
            <div class="detail-body">
            <div class="source-row">
              <a v-if="t.suno_url" class="source-pill" :href="t.suno_url" target="_blank" rel="noopener">
                <Icon name="music" size="sm" /> Suno 原件
              </a>
              <a v-if="t.r2_url" class="source-pill" :href="t.r2_url" target="_blank" rel="noopener">
                <Icon name="download" size="sm" /> R2 直链（可分发）
              </a>
              <span v-if="!t.audio_url" class="source-pill muted">本地无音频</span>
            </div>
            <audio v-if="t.audio_url" :src="t.audio_url" controls preload="none" class="track-audio" />
            </div>
          </div>

          <!-- 备料清单：「备料中」到底算不算完，之前界面上完全没说 -->
          <div v-for="(info, pk) in t.platforms" :key="`rd-${pk}`" class="detail-block">
            <template v-if="info.status === 'preparing'">
              <span class="detail-label">{{ platformLabel(pk) }} 备料清单</span>
              <div v-if="!readiness[`${t.id}|${pk}`]" class="detail-meta">
                <button class="ghost-btn small" @click="checkReady(t.id, pk)">检查还缺什么</button>
              </div>
              <template v-else>
                <div class="detail-body">
                <div v-for="it in readiness[`${t.id}|${pk}`].items" :key="it.名称"
                     class="ready-row" :class="{ miss: !it.就绪 }">
                  <Icon :name="it.就绪 ? 'check' : 'close'" size="sm" />
                  <span class="ready-name">{{ it.名称 }}</span>
                  <span v-if="!it.就绪" class="ready-hint">{{ it.说明 }}</span>
                </div>
                <div class="ready-foot">
                  <button v-if="readiness[`${t.id}|${pk}`].ok && readiness[`${t.id}|${pk}`].发布命令"
                          class="primary-btn small" @click="copyPublish(t.id, pk)">
                    <Icon name="save" size="sm" /><span>复制发布命令</span>
                  </button>
                  <span v-else-if="!readiness[`${t.id}|${pk}`].ok" class="ready-hint">
                    还缺 {{ readiness[`${t.id}|${pk}`].缺口数 }} 项，补齐了才能发
                  </span>
                  <a v-if="readiness[`${t.id}|${pk}`].控制台" class="source-pill"
                     :href="readiness[`${t.id}|${pk}`].控制台" target="_blank" rel="noopener">
                    打开{{ platformLabel(pk) }}后台
                  </a>
                </div>
                </div>
              </template>
            </template>
          </div>

          <div v-if="t.tags" class="detail-block">
            <span class="detail-label">风格</span>
            <span class="detail-tags">{{ t.tags }}</span>
          </div>
          <div v-if="t.lyrics" class="detail-block">
            <span class="detail-label">歌词</span>
            <pre class="detail-lyrics">{{ t.lyrics }}</pre>
          </div>
          <div v-for="(info, pk) in t.platforms" :key="pk" class="detail-block">
            <span class="detail-label">
              <PlatformMark :platform="pk" size="sm" />
              {{ platformLabel(pk) }}
            </span>
            <div class="detail-platform">
              <span class="meta-pill warn">{{ statusLabel(info.status) }}</span>
              <span v-if="info.submitted_at" class="detail-meta">
                提交于 {{ info.submitted_at.replace('T', ' ') }}
                <template v-if="waitedDays(info) !== null">· 已等 {{ waitedDays(info) }} 天</template>
              </span>
              <span v-else-if="info.status === 'preparing'" class="detail-meta">
                还没提交 —— 备料完成后跑
                <code>VF_TRACK={{ t.id }} browser-harness &lt; scripts/publish_{{ pk }}.py</code>
                自动填表，最后一步由你点提交
              </span>
              <p v-if="info.note" class="detail-meta">{{ info.note }}</p>
              <div v-if="info.config" class="detail-config">
                <template v-for="(v, k) in info.config" :key="k">
                  <div v-if="!k.startsWith('_') && typeof v !== 'object'" class="config-row">
                    <span class="config-k">{{ k }}</span><span class="config-v">{{ v }}</span>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>

    <!-- 确认发版弹窗。独家授权只能选一个平台；发行歌名必须唯一。 -->
    <n-modal v-model:show="showPublish" preset="card" title="确认发版" style="max-width: 480px">
      <p class="modal-lead">
        <strong>{{ publishTrack?.title }}</strong>
        <span v-if="publishTrack?.clip_id" class="modal-clip">Suno {{ publishTrack.clip_id.slice(0, 8) }}</span>
      </p>
      <p class="modal-hint">独家授权，只能投一个平台。汽水分发到网易云/QQ 不算再投。发出去的歌名必须唯一——Suno 生成名可以重复。</p>

      <label class="release-label">发行歌名</label>
      <input v-model="releaseTitle" class="release-input" maxlength="80" placeholder="发出去的名字，不能跟已发行的重复" />

      <div class="platform-picks">
        <label
          v-for="(p, pk) in platforms"
          :key="pk"
          class="platform-pick"
          :class="{ picked: pickedPlatform === pk }"
        >
          <input type="radio" :value="pk" v-model="pickedPlatform" />
          <PlatformMark :platform="pk" size="md" />
          <span class="pick-copy">
            <span class="pick-label">{{ p.label }}</span>
            <span class="pick-meta">
              {{ publishAccounts[pk]?.artist_name ? `账号 ${publishAccounts[pk].artist_name}` : '账号未同步' }}
              · 封面 {{ p.cover }}
            </span>
          </span>
        </label>
      </div>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showPublish = false">取消</n-button>
          <n-button type="primary" :loading="!!busyId" @click="confirmPublish">确认发版</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 导入下载目录 -->
    <n-modal v-model:show="showInbox" preset="card" title="从下载目录导入" style="max-width: 560px">
      <p class="modal-hint">
        Suno 下载的音频进 Downloads 后不会自动入库。挑要收的，工具复制进音乐库并登记为「已出歌」（原文件不动，重名自动加后缀）。
      </p>
      <n-spin :show="inboxLoading">
        <n-empty v-if="!inboxLoading && !inboxFiles.length" description="最近一周没有可导入的音频" />
        <div v-else class="inbox-list">
          <label v-for="f in inboxFiles" :key="f.path" class="inbox-item">
            <input
              type="checkbox"
              :value="f.path"
              v-model="pickedFiles"
              :disabled="f.in_library"
            />
            <span class="inbox-name" :title="f.path">{{ f.name }}</span>
            <span class="inbox-meta">
              {{ f.size_mb }} MB
              <span v-if="f.in_library" class="meta-pill success">已在库</span>
            </span>
          </label>
        </div>
      </n-spin>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showInbox = false">取消</n-button>
          <n-button
            type="primary"
            :loading="inboxImporting"
            :disabled="!pickedFiles.length"
            @click="doInboxImport"
          >
            导入选中（{{ pickedFiles.length }}）
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
/**
 * 作品流水线看板。
 *
 * ## 进度可视化升级
 *
 * 之前 5 个步骤只画圆点 + tooltip，扫一眼看不出「走到哪」。
 * 改成 n-steps 风格：圆点 + 文字 label + 连接线，已完成的打勾，
 * 当前的脉冲高亮。让看板一眼说人话。
 *
 * ## 「当前阶段」计数高亮
 *
 * 计数条里数字最多的那一列才值得关注 —— 那是流水线堵的地方。
 * 其他阶段都是上下文，给个 muted 就行。
 */
import { computed, onMounted, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { api, toMessage } from '../api';
import { usePipelineStore } from '../stores/pipeline';
import { useTasksStore } from '../stores/tasks';
import Icon from './Icon.vue';
import PlatformMark from './PlatformMark.vue';

const pipelineStore = usePipelineStore();
const tasksStore = useTasksStore();
const { stages, stageLabels, platforms, summary, tracks, error } = storeToRefs(pipelineStore);
const { tasks } = storeToRefs(tasksStore);

const coverJob = (trackId) =>
  (tasks.value || []).find(
    (x) =>
      ['queued', 'running'].includes(x.status)
      && ['cover', 'cover_upscale'].includes(x.type)
      && x.params?.track_id === trackId,
  );

const busyId = ref('');
const expanded = ref(new Set());
const toggleExpand = (id) => {
  const n = new Set(expanded.value);
  n.has(id) ? n.delete(id) : n.add(id);
  expanded.value = n;
};

// ── 封面出图（走 museav 中台）────────────────────────────
//
// 中台积分是硬约束：没了就出不了图。所以按钮的可用性绑在 can_generate 上
// （= 接了中台 **且** 余额够），而不是只看「接没接」—— 亮着但点下去必然
// 失败的按钮，比灰掉的按钮更让人困惑。
const coverBusyId = ref('');
const coverCaps = ref({
  can_generate: false, credits: 0, est_cny: 0, detail: '检查中…',
  common_ratios: [], sizes: {}, cover_side: 1440,
});

// 当前比例会出多大的图。常用比例后端已经算好；自定义比例算不出来就不显示 ——
// 与其显示一个猜的数，不如什么都不说。
const coverSize = computed(() => coverCaps.value.sizes?.[coverRatio.value] || '');

// 出封面的画幅。用 <input list> 而不是 <select>：中台支持**任意** W:H
// （中台支持任意尺寸），下拉里那几个只是
// 常用值。用 select 就把上游的能力锁死在五个枚举上了。
//
// 记在 localStorage：这是「我这批封面用什么画幅」的偏好，每次打开都要重选很烦。
const coverRatio = ref(localStorage.getItem('vf.coverRatio') || '1:1');
watch(coverRatio, (v) => {
  try { localStorage.setItem('vf.coverRatio', v || '1:1'); } catch { /* 隐私模式下会抛，忽略 */ }
});

const coverBtnLabel = computed(() => {
  if (!coverCaps.value.can_generate) {
    // 措辞不写「积分不足」—— 那暗示「去充值」，而余额为 0 也可能只是
    // 中台那边的额度配置（自家租户本来就不该被闸门卡）。
    // 把配置问题写成消费问题，会让人朝错误的方向排查。
    return coverCaps.value.credits === 0 ? '中台额度闸门拦住' : '出封面（不可用）';
  }
  return `出封面 ≈¥${(coverCaps.value.est_cny || 0).toFixed(2)}`;
});

const loadCoverCaps = async () => {
  try { coverCaps.value = await api.coverStatus(); } catch { /* 查不到就保持不可用 */ }
};

const genCover = async (t) => {
  coverBusyId.value = t.id;
  try {
    const { task_id } = await api.generateCover({
      track_id: t.id, title: t.title, tags: t.tags || '',
      ratio: coverRatio.value || '1:1',
    });
    tasksStore.showToast(`封面出图已提交（约 ¥${(coverCaps.value.est_cny || 0).toFixed(2)}）`, 'info');
    const done = await waitTask(task_id);
    if (done?.status === 'done') {
      tasksStore.showToast('封面已生成并回填台账', 'success');
      await load();
    } else {
      await tasksStore.reportError(new Error(done?.error || '出图失败'), { action: 'cover.generate' });
    }
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'cover.generate' });
  } finally {
    coverBusyId.value = '';
    loadCoverCaps();
  }
};

const upscaleCover = async (t) => {
  coverBusyId.value = t.id;
  try {
    const { task_id } = await api.upscaleCover({ track_id: t.id });
    tasksStore.showToast('本地超分已提交（不花积分）', 'info');
    const done = await waitTask(task_id);
    if (done?.status === 'done') {
      tasksStore.showToast('封面已超分到 1440 并回填台账', 'success');
      await load();
    } else {
      await tasksStore.reportError(new Error(done?.error || '超分失败'), { action: 'cover.upscale' });
    }
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'cover.upscale' });
  } finally {
    coverBusyId.value = '';
  }
};

/** 轮询到任务终态。1 秒一次、最多 5 分钟 —— 进度条要跟得上。 */
const waitTask = async (taskId) => {
  for (let i = 0; i < 300; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      const { tasks } = await api.tasks();
      const t = tasks.find((x) => x.id === taskId);
      if (t && ['done', 'error', 'cancelled'].includes(t.status)) return t;
    } catch { /* 单次查询失败不算数，下一轮再试 */ }
  }
  return null;
};

const showPublish = ref(false);
const publishTrack = ref(null);
const pickedPlatform = ref('');
const releaseTitle = ref('');
const publishAccounts = ref({});

const load = async () => {
  try {
    await pipelineStore.loadPipeline();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'pipeline.load' });
  }
};
onMounted(() => { load(); loadCoverCaps(); });
defineExpose({ load });

// 下载目录导入
const showInbox = ref(false);
const inboxFiles = ref([]);
const inboxLoading = ref(false);
const inboxImporting = ref(false);
const pickedFiles = ref([]);

const openInbox = async () => {
  showInbox.value = true;
  pickedFiles.value = [];
  inboxLoading.value = true;
  try {
    const data = await api.inbox();
    inboxFiles.value = data.files || [];
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'inbox.list' });
  } finally {
    inboxLoading.value = false;
  }
};

const doInboxImport = async () => {
  if (!pickedFiles.value.length) {
    tasksStore.showToast('先勾选要导入的文件', 'warning');
    return;
  }
  inboxImporting.value = true;
  try {
    const data = await api.inboxImport(pickedFiles.value);
    tasksStore.showToast(`已导入 ${data.count} 个文件到「已出歌」`, 'success');
    showInbox.value = false;
    await load();
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'inbox.import', tags: { count: pickedFiles.value.length } });
  } finally {
    inboxImporting.value = false;
  }
};

const counters = computed(() =>
  stages.value.map((s) => ({ key: s, label: stageLabels.value[s] || s, n: summary.value[s] || 0 })),
);

/** 找出作品数最多的阶段 —— 那是流水线堵的地方 */
const currentStageKey = computed(() => {
  let maxN = 0;
  let maxKey = '';
  for (const c of counters.value) {
    if (c.n > maxN) { maxN = c.n; maxKey = c.key; }
  }
  return maxKey;
});

const stageIndex = (s) => stages.value.indexOf(s);

const stepClass = (currentStage, stage, index) => {
  const ci = stageIndex(currentStage);
  if (index < ci) return 'done';
  if (index === ci) return 'current';
  return 'pending';
};

const nextAction = (track) => {
  switch (track.stage) {
    case 'draft':      return { label: '标记已出歌', to: 'generated', type: 'default' };
    case 'generated':  return { label: '选定这首', to: 'selected', type: 'primary' };
    case 'selected':   return { label: '确认发版', to: 'publishing', type: 'primary', needsPlatform: true };
    case 'publishing': return { label: '标记已上架', to: 'published', type: 'success' };
    default:           return null;
  }
};

const advance = async (track) => {
  const action = nextAction(track);
  if (!action) return;
  if (action.needsPlatform) {
    publishTrack.value = track;
    pickedPlatform.value = track.release_platform || '';
    releaseTitle.value = track.release_title || track.title || '';
    showPublish.value = true;
    api.platformAccounts().then((d) => { publishAccounts.value = d.accounts || {}; }).catch(() => {});
    return;
  }
  busyId.value = track.id;
  try {
    await pipelineStore.setStage(track.id, action.to);
    // 「标记已上架」必须**连平台状态一起改**，否则会出现自相矛盾的行：
    // 流水线写着「已上架」，平台那栏还停在「备料中」。
    // 两个状态各说各话之后，这张看板就没法用来回答「这歌到底发出去没有」。
    if (action.to === 'published') {
      const inflight = Object.entries(track.platforms || {})
        .filter(([, i]) => ['preparing', 'uploaded', 'reviewing'].includes(i?.status));
      for (const [pk] of inflight) {
        await pipelineStore.setPlatformStatus({ track_id: track.id, platform: pk, status: 'online' });
      }
    }
    await load();
    tasksStore.showToast(`「${track.title}」→ ${stageLabels.value[action.to]}`, 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'pipeline.advance', tags: { trackId: track.id, to: action.to } });
  } finally {
    busyId.value = '';
  }
};

const confirmPublish = async () => {
  if (!pickedPlatform.value) {
    tasksStore.showToast('独家授权，先选一个平台', 'warning');
    return;
  }
  const title = (releaseTitle.value || '').trim();
  if (!title) {
    tasksStore.showToast('发行歌名不能空', 'warning');
    return;
  }
  const track = publishTrack.value;
  busyId.value = track.id;
  try {
    await pipelineStore.submitRelease({
      track_id: track.id,
      platform: pickedPlatform.value,
      release_title: title,
    });
    await load();
    showPublish.value = false;
    tasksStore.showToast(`「${title}」独家发往 ${platformLabel(pickedPlatform.value)}`, 'success');
  } catch (cause) {
    await tasksStore.reportError(cause, {
      action: 'pipeline.publish',
      tags: { trackId: track.id, platform: pickedPlatform.value },
    });
  } finally {
    busyId.value = '';
  }
};

// 批量操作
const selectedIds = ref(new Set());
const batchBusy = ref(false);

const toggleSelect = (id) => {
  const n = new Set(selectedIds.value);
  n.has(id) ? n.delete(id) : n.add(id);
  selectedIds.value = n;
};

const canBatchAdvance = (t) => {
  const action = nextAction(t);
  return !!action && !action.needsPlatform;
};

const batchAdvance = async () => {
  const targets = tracks.value.filter((t) => selectedIds.value.has(t.id) && canBatchAdvance(t));
  if (!targets.length) {
    tasksStore.showToast('勾选的作品里没有可批量推进的（发版那步需单独选平台）', 'warning');
    return;
  }
  batchBusy.value = true;
  let okCount = 0;
  const failed = [];
  for (const t of targets) {
    const action = nextAction(t);
    try {
      await pipelineStore.setStage(t.id, action.to);
      okCount += 1;
    } catch {
      failed.push(t.title);
    }
  }
  batchBusy.value = false;
  selectedIds.value = new Set();
  await load();
  if (failed.length) {
    tasksStore.showToast(`推进 ${okCount} 首；失败 ${failed.length} 首（${failed.slice(0, 3).join('、')}…）`, 'warning');
  } else {
    tasksStore.showToast(`已批量推进 ${okCount} 首`, 'success');
  }
};

const platformLabel = (key) => platforms.value?.[key]?.label || key;

/**
 * 备料清单，按 `trackId|platform` 缓存。
 *
 * 不在 load() 里一次性全查：看板可能有几十首，而备料清单只有展开
 * 「备料中」那几首时才有意义 —— 为了不看的东西打几十个请求不划算。
 */
const readiness = ref({});

const checkReady = async (trackId, platform) => {
  try {
    readiness.value = { ...readiness.value, [`${trackId}|${platform}`]: await api.readiness(trackId, platform) };
  } catch (cause) {
    await tasksStore.reportError(cause, { action: 'pipeline.readiness', tags: { trackId, platform } });
  }
};

/**
 * 把发布命令放进剪贴板。
 *
 * 为什么是复制命令而不是一个「立即发布」按钮：填表要驱动**你本机那个
 * 已登录的浏览器**，服务端替你点不了；而且最后那一下提交是不可逆的
 * （进了审核队列要撤回），值得你自己看一眼再按。
 * 自动化省的是填表那 10 分钟，不是点提交那 1 秒。
 */
const copyPublish = async (trackId, platform) => {
  const cmd = readiness.value[`${trackId}|${platform}`]?.发布命令 || '';
  if (!cmd) return;
  try {
    await navigator.clipboard.writeText(cmd);
    tasksStore.showToast('命令已复制 —— 在项目目录里粘贴执行，会自动填表并停在提交前', 'success');
  } catch {
    tasksStore.showToast(cmd, 'info');   // 剪贴板被拒（非 https）就直接显示出来
  }
};

const PLATFORM_STATUS = {
  preparing: '备料中',
  uploaded: '已上传',
  reviewing: '审核中',
  online: '已上架',
  rejected: '被驳回',
};
const statusLabel = (s) => PLATFORM_STATUS[s] || s;

/**
 * 已提交审核多少天。不在审核中、或没有提交时间就返回 null（不显示）。
 *
 * 为什么要显示这个：审核状态本身是**静止的**，voxflow 不会去平台轮询，
 * 所以「审核中」这三个字放三天和放三十天长得一模一样。
 * 汽水承诺 1-2 个工作日 —— 逆着风跑起来 8-30 提交，直到 9-6 才被发现
 * 卡了 7 天，就是因为界面上看不出时间在流逝。
 *
 * 超过 3 天标红：那已经超过任何平台承诺的审核时长，该去后台查了。
 */
const waitedDays = (info) => {
  if (info?.status !== 'reviewing' || !info?.submitted_at) return null;
  const t = Date.parse(info.submitted_at);
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86400000);
};
</script>

<style scoped>
.detail-body { flex: 1; min-width: 0; }
.source-row { display: flex; flex-wrap: wrap; gap: var(--vf-space-2); margin-bottom: var(--vf-space-2); }
.source-pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 999px; font-size: 12px;
  background: var(--vf-bg-3, rgba(255,255,255,.06));
  color: var(--vf-text-2, #bbb); text-decoration: none;
}
.source-pill:hover { color: var(--vf-text-1, #fff); }
.source-pill.muted { opacity: .5; }
.ready-row { display: flex; align-items: baseline; gap: 6px; font-size: 12px; padding: 2px 0; }
.ready-row.miss { color: #ff7a5c; }
.ready-name { min-width: 9em; }
.ready-hint { color: var(--vf-text-3, #888); }
.ready-foot { display: flex; align-items: center; gap: var(--vf-space-2); margin-top: var(--vf-space-2); }
.wait-badge {
  margin-left: var(--vf-space-1);
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
  background: var(--vf-bg-3, rgba(255,255,255,.08));
  color: var(--vf-text-3, #999);
}
/* 超期就必须扎眼 —— 这条信息的全部价值就在于被看见 */
.wait-badge.overdue {
  background: rgba(255, 99, 71, .18);
  color: #ff7a5c;
  font-weight: 600;
}
.board-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
  padding: 0 var(--vf-space-2);
  max-width: 1080px;
  margin: 0 auto;
  width: 100%;
}

/* head */
.board-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.board-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.board-tools { display: flex; gap: var(--vf-space-2); align-items: center; }
.ratio-pick {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px 0 10px;
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  background: var(--vf-bg-2);
}
.ratio-label { font-size: 11px; color: var(--vf-text-3); white-space: nowrap; }
.ratio-input {
  width: 62px;
  background: transparent;
  border: none;
  outline: none;
  color: var(--vf-text-1);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  padding: 5px 4px;
}
.ratio-input::placeholder { color: var(--vf-text-4); }
.ratio-size {
  font-size: 11px;
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
  padding-right: 8px;
  white-space: nowrap;
}

/* counters */
.counters {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--vf-space-2);
}
.counter {
  padding: var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  text-align: center;
  transition: all 0.15s var(--vf-ease);
}
.counter.is-zero { opacity: 0.4; }
.counter.is-current {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
}
.counter-n {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: var(--vf-primary);
  font-variant-numeric: tabular-nums;
}
.counter-label { font-size: 11px; color: var(--vf-text-3); margin-top: 2px; }

.board-err { margin-bottom: var(--vf-space-3); }

/* empty */
.board-empty { padding: var(--vf-space-8) 0; }
.empty-hint { font-size: 12px; color: var(--vf-text-3); margin: 0 0 var(--vf-space-3); }

/* track */
.track-list { display: flex; flex-direction: column; gap: var(--vf-space-3); }
.track {
  padding: var(--vf-space-4);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
}
.batch-bar {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  border: 1px dashed var(--vf-primary);
  border-radius: var(--vf-radius-md);
  background: var(--vf-primary-soft);
  flex-wrap: wrap;
}
.batch-count { font-weight: 600; color: var(--vf-primary); }
.batch-hint { margin-left: auto; font-size: 11px; color: var(--vf-text-3); }

.track-check {
  display: flex;
  align-items: flex-start;
  padding-top: 22px;
  cursor: pointer;
  flex: none;
}
.track-check input {
  width: 16px;
  height: 16px;
  accent-color: var(--vf-primary);
  cursor: pointer;
}
.track-check-spacer { width: 16px; flex: none; padding-top: 22px; }

.track-head { display: flex; gap: var(--vf-space-3); align-items: flex-start; }
.track-cover {
  width: 64px; height: 64px;
  border-radius: var(--vf-radius-md);
  object-fit: cover;
  background: var(--vf-bg-3);
  flex: none;
}
.track-cover-empty {
  display: flex; align-items: center; justify-content: center;
  color: var(--vf-text-3); font-size: 22px;
}
.track-main { flex: 1; min-width: 0; }
.track-title-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-1);
  flex-wrap: wrap;
}
.track-title {
  font-weight: 600;
  color: var(--vf-text-1);
  font-size: 14px;
}
.track-id-row {
  display: flex; flex-wrap: wrap; gap: var(--vf-space-2);
  margin: 0 0 var(--vf-space-2);
}
.stage-pill {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
}
.stage-pill.stage-generated { background: var(--vf-primary-soft); color: var(--vf-primary); }
.stage-pill.stage-selected { background: rgba(95, 125, 149, 0.15); color: var(--vf-info); }
.stage-pill.stage-publishing { background: var(--vf-warn-soft); color: var(--vf-warn); }
.stage-pill.stage-published { background: var(--vf-ok-soft); color: var(--vf-ok); }

.track-desc {
  margin: 0 0 var(--vf-space-2);
  font-size: 12px; line-height: 1.6;
  color: var(--vf-text-2);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.track-audio { width: 100%; height: 30px; margin-top: var(--vf-space-2); }

/* steps */
.steps {
  display: flex;
  align-items: center;
  gap: 0;
  margin: var(--vf-space-3) 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.steps::-webkit-scrollbar { display: none; }
.step {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}
.step-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1.5px solid var(--vf-border-strong);
  background: var(--vf-bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vf-text-3);
  transition: all 0.2s var(--vf-ease);
  flex: none;
}
.step-label {
  font-size: 11px;
  color: var(--vf-text-3);
  white-space: nowrap;
}
.step.done .step-dot {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  color: white;
}
.step.done .step-label { color: var(--vf-text-1); }
.step.current .step-dot {
  background: var(--vf-primary);
  border-color: var(--vf-primary);
  color: white;
  box-shadow: 0 0 0 4px var(--vf-primary-soft);
  animation: step-pulse 1.5s ease-in-out infinite;
}
.step.current .step-label { color: var(--vf-primary); font-weight: 600; }
@keyframes step-pulse {
  0%, 100% { box-shadow: 0 0 0 4px var(--vf-primary-soft); }
  50% { box-shadow: 0 0 0 7px transparent; }
}

.step-line {
  flex: 1;
  height: 1.5px;
  background: var(--vf-border);
  min-width: 12px;
  margin: 0 4px;
}
.step-line.done { background: var(--vf-primary); opacity: 0.6; }

.track-progress { margin-top: var(--vf-space-2); }
.track-progress-bar {
  height: 4px;
  background: var(--vf-bg-3);
  border-radius: var(--vf-radius-full);
  overflow: hidden;
}
.track-progress-fill {
  height: 100%;
  background: var(--vf-primary);
  border-radius: var(--vf-radius-full);
  transition: width 0.3s var(--vf-ease);
}
.track-progress-label {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--vf-text-3);
}

/* track foot */
.track-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-3);
  margin-top: var(--vf-space-3);
  flex-wrap: wrap;
}
.track-tags { display: flex; gap: var(--vf-space-2); flex-wrap: wrap; }
.track-actions { display: flex; gap: var(--vf-space-2); }
.meta-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 3px 8px;
  background: var(--vf-bg-3);
  border-radius: var(--vf-radius-full);
  color: var(--vf-text-2);
}
.meta-pill.warn { background: var(--vf-warn-soft); color: var(--vf-warn); }
.meta-pill.success { background: var(--vf-ok-soft); color: var(--vf-ok); }

/* buttons */
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
.ghost-btn:hover:not(:disabled) {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.ghost-btn.small { padding: 4px 10px; font-size: 11px; }
.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-primary);
  border: 1px solid var(--vf-primary);
  color: white;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.primary-btn:hover:not(:disabled) {
  background: var(--vf-primary-hover);
  border-color: var(--vf-primary-hover);
  transform: translateY(-1px);
}
.primary-btn.small { padding: 5px 10px; font-size: 11px; }
.primary-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.primary-btn.action-success { background: var(--vf-ok); border-color: var(--vf-ok); }
.primary-btn.action-success:hover:not(:disabled) { background: #16a34a; border-color: #16a34a; }
.primary-btn.action-default { background: var(--vf-bg-3); color: var(--vf-text-1); border-color: var(--vf-border); }
.primary-btn.action-default:hover:not(:disabled) { background: var(--vf-bg-hover); border-color: var(--vf-border-strong); }

/* detail */
.track-detail {
  margin-top: var(--vf-space-3);
  padding-top: var(--vf-space-3);
  border-top: 1px solid var(--vf-border);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.detail-block { display: flex; gap: var(--vf-space-3); font-size: 12px; }
.detail-label {
  flex: none;
  min-width: 56px;
  color: var(--vf-text-3);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.detail-tags { color: var(--vf-text-2); line-height: 1.6; }
.detail-lyrics {
  margin: 0;
  flex: 1;
  max-height: 220px;
  overflow-y: auto;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.8;
  color: var(--vf-text-2);
  white-space: pre-wrap;
}
.detail-platform { flex: 1; display: flex; flex-direction: column; gap: var(--vf-space-1); }
.detail-meta { margin: 0; font-size: 11px; color: var(--vf-text-3); }
.detail-config {
  margin-top: var(--vf-space-1);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.config-row { display: flex; gap: var(--vf-space-2); font-size: 11px; }
.config-k { flex: none; width: 96px; color: var(--vf-text-3); }
.config-v { color: var(--vf-text-2); }

/* modals */
.modal-lead { margin: 0 0 var(--vf-space-2); color: var(--vf-text-1); }
.modal-clip { margin-left: var(--vf-space-2); font-size: 12px; color: var(--vf-text-3); }
.modal-hint { margin: 0 0 var(--vf-space-4); font-size: 12px; color: var(--vf-text-3); }
.release-label { display: block; font-size: 12px; color: var(--vf-text-3); margin-bottom: 4px; }
.release-input {
  width: 100%; margin-bottom: var(--vf-space-4);
  padding: 8px 10px; border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm); background: var(--vf-bg-3);
  color: var(--vf-text-1); font-size: 13px;
}

.platform-picks { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.platform-pick {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  cursor: pointer;
  transition: background 0.15s;
}
.platform-pick:hover { background: var(--vf-bg-3); }
.platform-pick.picked { border-color: var(--vf-primary); background: var(--vf-primary-soft); }
.pick-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pick-label { color: var(--vf-text-1); }
.pick-meta { font-size: 11px; color: var(--vf-text-3); }

.inbox-list { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.inbox-item {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.inbox-item:hover { background: var(--vf-bg-3); }
.inbox-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inbox-meta { display: flex; align-items: center; gap: var(--vf-space-2); font-size: 12px; color: var(--vf-text-3); }

@media (max-width: 760px) {
  .counters { grid-template-columns: repeat(5, 1fr); font-size: 10px; }
  .counter-n { font-size: 18px; }
}
</style>
