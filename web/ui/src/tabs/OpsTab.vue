<template>
  <div class="tab-content-container">
    <!-- 顶部：一眼看完的三个数 -->
    <section class="kpi-row">
      <div class="kpi kpi-cost">
        <div class="kpi-label">近 {{ days }} 天开销</div>
        <div class="kpi-value">¥{{ fmt(eco?.summary.total_cny) }}</div>
        <div class="kpi-sub">
          {{ eco?.summary.by_provider.length || 0 }} 个上游 · {{ totalCalls }} 次调用
          <template v-if="(eco?.summary.estimated_cny || 0) > 0">
            · 含 ¥{{ fmt(eco?.summary.estimated_cny) }} 估算
          </template>
        </div>
      </div>
      <div class="kpi kpi-saved">
        <div class="kpi-label">本地跑省下</div>
        <div class="kpi-value">¥{{ fmt(eco?.summary.saved_cny) }}</div>
        <div class="kpi-sub">同样的量走商业 API 要 ¥{{ fmt(marketTotal) }}</div>
      </div>
      <div class="kpi kpi-earn">
        <div class="kpi-label">累计收益</div>
        <div class="kpi-value">¥{{ fmt(eco?.pnl.lifetime_earned_cny) }}</div>
        <div class="kpi-sub">
          {{ (eco?.pnl.total_plays || 0).toLocaleString() }} 次播放 ·
          实测 ¥{{ (eco?.pnl.cny_per_1k_plays_measured || 0).toFixed(2) }}/千播
        </div>
      </div>
      <div class="kpi">
        <div class="kpi-label">单曲均价</div>
        <div class="kpi-value">¥{{ fmt(eco?.avg_cost_per_track_cny) }}</div>
        <div class="kpi-sub">
          <template v-if="eco?.avg_breakeven_plays">
            播 {{ eco.avg_breakeven_plays.toLocaleString() }} 次回本
          </template>
          <template v-else>还没有计过量的作品</template>
        </div>
      </div>
      <div class="kpi" :class="`kpi-health-${health?.status || 'unknown'}`">
        <div class="kpi-label">系统状态</div>
        <div class="kpi-value kpi-value-sm">
          <span class="dot" />{{ HEALTH_LABEL[health?.status || 'unknown'] }}
        </div>
        <div class="kpi-sub">已运行 {{ uptime }}</div>
      </div>
    </section>

    <!-- 计量覆盖率提示：0 元不等于免费，可能只是没记账 -->
    <WarnBanner
      v-if="eco && eco.covered < eco.total_tracks"
      type="info"
      :title="`${eco.total_tracks} 首作品里有 ${eco.total_tracks - eco.covered} 首没有成本数据`"
      :hint="`那是接入计量之前做的（多数是从平台同步回来的历史作品）。它们显示 ¥0 是「没记账」，不是「没花钱」—— 之后新做的作品会自动计入。`"
    />

    <n-tabs v-model:value="pane" type="line" animated class="ops-tabs">
      <!-- ══ 生意 ══ -->
      <n-tab-pane name="business" tab="这门生意">
        <div class="pane-body">
          <!-- 收入侧：这门生意真正赚回来的钱 -->
          <section class="card">
            <div class="section-title">
              <Icon name="trend-up" size="sm" />
              <span>赚回来多少</span>
              <span class="title-hint">数据来自各平台后台，由 scripts/sync_*.py 同步</span>
            </div>
            <div v-if="!revenueRows.length" class="empty">
              还没有平台收益数据。跑一次 <code>scripts/sync_netease.py</code> 之类的同步脚本。
            </div>
            <div v-else class="rev-grid">
              <div v-for="r in revenueRows" :key="r.key" class="rev-card">
                <div class="rev-head">
                  <span class="rev-name">
                    <PlatformMark :platform="r.key" size="sm" />
                    {{ r.label }}
                  </span>
                  <span class="rev-earn">¥{{ fmt(r.earned_cny) }}</span>
                </div>
                <div v-if="r.artist" class="rev-artist">{{ r.artist }}</div>
                <div class="rev-stats">
                  <span>{{ r.songs }} 首在线</span>
                  <span>{{ r.plays.toLocaleString() }} 播放</span>
                  <span>{{ r.fans }} 粉丝</span>
                </div>
                <div class="rev-rate">
                  ¥{{ r.cny_per_1k_plays.toFixed(3) }}/千播
                  <span class="src" :class="r.rate_source">
                    {{ r.rate_source === 'measured' ? '实测' : '估算' }}
                  </span>
                </div>
                <div v-if="r.plays_7d" class="rev-7d">
                  近 7 天 {{ r.plays_7d }} 次播放<template v-if="r.plays_7d < 200">
                    <span class="warn-text"> · 增长已基本停滞</span>
                  </template>
                </div>
              </div>
            </div>
            <p class="foot-note">
              标「实测」的千播单价是<b>后台可提现金额 ÷ 累计播放量</b>反推出来的 ——
              比公开资料的区间中位数准，因为它已经包含了这个账号的实际权益档位。
              标「估算」的还没有收益数据，用的是 <code>configs/pricing.json</code> 里的公开值。
            </p>
          </section>

          <!-- 成本构成 -->
          <section class="card">
            <div class="section-title">
              <Icon name="wallet" size="sm" />
              <span>钱花在哪</span>
              <span class="title-hint">近 {{ days }} 天</span>
            </div>
            <div v-if="!eco?.summary.by_provider.length" class="empty">
              还没有计量数据。生成一首歌或合成一段语音之后，这里就有数了。
            </div>
            <div v-else class="prov-list">
              <div v-for="p in eco.summary.by_provider" :key="p.provider" class="prov-row">
                <div class="prov-head">
                  <span class="prov-name">{{ providerLabel(p.provider) }}</span>
                  <span class="prov-cost" :class="{ free: !p.cost_cny }">
                    {{ p.cost_cny ? `¥${fmt(p.cost_cny)}` : '免费' }}
                  </span>
                </div>
                <div class="prov-bar">
                  <div class="prov-bar-fill" :style="{ width: barWidth(p.cost_cny) }" />
                </div>
                <div class="prov-meta">
                  {{ p.n }} 次 · {{ fmtQty(p) }}
                  <template v-if="p.failed">
                    · <span class="err-text">{{ p.failed }} 次失败{{ failedNote(p) }}</span>
                  </template>
                  <template v-if="p.saved_cny > 0">
                    · <span class="ok-text">省下 ¥{{ fmt(p.saved_cny) }}</span>
                  </template>
                  <template v-if="(p.estimated_cny || 0) > 0">
                    · <span class="est-tag">¥{{ fmt(p.estimated_cny) }} 为回填估算</span>
                  </template>
                </div>
              </div>
            </div>
          </section>

          <!-- 单曲成本 + 回本 -->
          <section class="card">
            <div class="section-title">
              <Icon name="trend-up" size="sm" />
              <span>每首歌：花了多少 · 赚回多少 · 回本没有</span>
              <span v-if="eco" class="title-hint">
                {{ eco.revenue_covered }} 首有单曲收入数据
              </span>
            </div>
            <div v-if="!eco?.tracks.length" class="empty">
              还没有作品的成本记录。
            </div>
            <div v-else class="table-scroll">
              <table class="cost-table">
                <thead>
                  <tr>
                    <th>作品</th>
                    <th class="num">成本</th>
                    <th class="num">近 30 日播放</th>
                    <th class="num">折算收益</th>
                    <th class="num">ROI</th>
                    <th class="num">回本还差</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="t in eco.tracks" :key="t.track_id">
                    <td class="ttl" :title="t.track_id">{{ t.title }}</td>
                    <td class="num strong">{{ t.cost_cny ? `¥${fmt(t.cost_cny)}` : '—' }}</td>
                    <!-- null 和 0 要分开显示：null 是「还没抓数据」，
                         0 是「真的一次没播」，两者该采取的行动完全不同。 -->
                    <td class="num">{{ t.plays === null ? '—' : t.plays.toLocaleString() }}</td>
                    <td class="num">{{ t.earned_cny === null ? '—' : `¥${fmt(t.earned_cny)}` }}</td>
                    <td class="num" :class="roiClass(t.roi)">{{ roiText(t.roi) }}</td>
                    <td class="num">{{ gapText(t) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="foot-note">
              <b>播放量</b>是网易云音乐人后台的近 30 日数据（公开 API 给不了 ——
              <code>playedNum</code> 恒为 0）。跑 <code>scripts/ncm_track_stats.py</code> 更新，需登录。
              <br />
              <b>折算收益</b> = 播放量 × 实测千播单价（账号总收益 ÷ 账号总播放）。
              后台没有单曲收益列，所以这是<b>折算值不是平台实付</b> ——
              网易云按播放计费、同账号各曲单价基本相同，折算站得住，但别当成对账依据。
              <br />
              「—」表示没有数据，不是 0。两者含义完全不同：前者是还没抓，后者是真的没播。
            </p>
          </section>
        </div>
      </n-tab-pane>

      <!-- ══ 系统 ══ -->
      <n-tab-pane name="system" tab="系统健康">
        <div class="pane-body">
          <section class="card">
            <div class="section-title">
              <Icon name="pulse" size="sm" />
              <span>体检项</span>
              <button class="ghost-btn" @click="refresh">
                <Icon name="refresh" size="sm" /> 刷新
              </button>
            </div>
            <div class="check-grid">
              <div
                v-for="(c, k) in health?.checks || {}"
                :key="k"
                class="check"
                :class="checkClass(c)"
              >
                <div class="check-head">
                  <Icon :name="c.ok ? (c.warn ? 'warning' : 'check') : 'close'" size="sm" />
                  <span>{{ CHECK_LABEL[String(k)] || k }}</span>
                </div>
                <div class="check-detail">{{ c.detail }}</div>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="section-title">
              <Icon name="clock" size="sm" />
              <span>接口性能</span>
              <span class="title-hint">P95 是「最慢的那 5% 有多慢」，比平均值更能反映卡顿</span>
            </div>
            <div v-if="!metrics?.routes.length" class="empty">进程刚起，还没有请求样本。</div>
            <div v-else class="table-scroll">
              <table class="cost-table">
                <thead>
                  <tr>
                    <th>端点</th>
                    <th class="num">调用</th>
                    <th class="num">错误率</th>
                    <th class="num">P50</th>
                    <th class="num">P95</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in metrics.routes" :key="r.key">
                    <td class="mono">{{ r.key }}</td>
                    <td class="num">{{ r.n }}</td>
                    <td class="num" :class="{ 'err-text': r.error_rate > 0 }">
                      {{ (r.error_rate * 100).toFixed(1) }}%
                    </td>
                    <td class="num">{{ r.p50_ms }}ms</td>
                    <td class="num" :class="{ 'warn-text': r.p95_ms > 2000 }">{{ r.p95_ms }}ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </n-tab-pane>

      <!-- ══ 日志 ══ -->
      <n-tab-pane name="logs" tab="运行日志">
        <div class="pane-body">
          <section class="card">
            <div class="section-title">
              <Icon name="layers" size="sm" />
              <span>最近事件</span>
              <n-radio-group v-model:value="logLevel" size="small" @update:value="loadLogs">
                <n-radio-button value="" label="全部" />
                <n-radio-button value="warn" label="警告" />
                <n-radio-button value="error" label="错误" />
              </n-radio-group>
            </div>
            <div v-if="!logs.length" class="empty">
              这个级别下没有日志 —— 对错误级别来说，空的是好事。
            </div>
            <div v-else class="log-list">
              <div v-for="(l, i) in logs" :key="i" class="log-row" :class="`lv-${l.level}`">
                <span class="log-ts">{{ l.ts.slice(11) }}</span>
                <span class="log-event">{{ l.event }}</span>
                <span class="log-rest">{{ rest(l) }}</span>
              </div>
            </div>
            <p class="foot-note">
              只记失败和超过 3 秒的慢请求 —— 全量记的话一天几万行，
              真正要找的那条反而被淹掉。量的信息在「接口性能」里。日志保留 14 天。
            </p>
          </section>
        </div>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
/**
 * 运营台 —— 「这门生意花了多少钱」和「这台机器还好吗」。
 *
 * ## 为什么这两件事在同一屏
 *
 * 它们是同一个问题的两面：出歌失败会扣积分（成本），磁盘满了会让合成
 * 静默失败（既是故障也是浪费）。分成两屏的话，看成本的人看不到失败率，
 * 看健康的人不知道那些失败花了多少钱。
 *
 * ## 刷新节奏
 *
 * 健康 15 秒、指标 15 秒、成本 60 秒。成本是累积量，秒级刷新没有信息增益，
 * 只是白跑聚合查询；健康要能及时看见磁盘或队列出问题。
 *
 * 切走这一屏就停轮询 —— 后台屏幕接着打接口是最典型的白耗电。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { api, toMessage } from '../api';
import Icon from '../components/Icon.vue';
import PlatformMark from '../components/PlatformMark.vue';
import WarnBanner from '../components/WarnBanner.vue';
import type { EconomicsResponse, HealthResponse, LogRecord, MetricsResponse, ProviderUsage, TrackEconomics } from '../types/api';

const days = 30;
const pane = ref('business');
const eco = ref<EconomicsResponse | null>(null);
const health = ref<HealthResponse | null>(null);
const metrics = ref<MetricsResponse | null>(null);
const logs = ref<LogRecord[]>([]);
const logLevel = ref('');

const HEALTH_LABEL: Record<string, string> = {
  ok: '一切正常', degraded: '能用，有隐患', down: '有项目坏了', unknown: '检查中',
};
const CHECK_LABEL: Record<string, string> = {
  database: '台账数据库', data_dir: '数据目录可写', disk: '磁盘空间',
  tts_models: 'TTS 模型', task_queue: '任务队列',
};

const fmt = (n?: number) => (n ?? 0).toFixed(2);
const plays = (n: number) => (n > 0 ? n.toLocaleString() : '—');

/** ROI ≥1 是回本了，<1 是还在亏。null 是没数据 —— 不要显示成 0。 */
const roiText = (roi: number | null) => (roi === null ? '—' : `${roi.toFixed(2)}x`);
const roiClass = (roi: number | null) =>
  (roi === null ? '' : roi >= 1 ? 'ok-text' : roi > 0 ? 'warn-text' : 'err-text');

/** 还差多少次播放回本。已回本显示「已回本」，没成本数据的不算。 */
const gapText = (t: TrackEconomics) => {
  if (!t.cost_cny) return '—';
  const need = t.breakeven_plays.netease;
  if (!need) return '—';
  if (t.plays === null) return `需 ${need.toLocaleString()} 次`;
  const left = need - t.plays;
  return left <= 0 ? '已回本' : `还差 ${left.toLocaleString()} 次`;
};

const totalCalls = computed(() =>
  (eco.value?.summary.by_provider || []).reduce((s, p) => s + p.n, 0));
const marketTotal = computed(() =>
  (eco.value?.summary.by_provider || []).reduce((s, p) => s + (p.market_cny || 0), 0));

const uptime = computed(() => {
  const s = health.value?.uptime_s ?? 0;
  if (s < 60) return `${s} 秒`;
  if (s < 3600) return `${Math.floor(s / 60)} 分钟`;
  return `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`;
});

/** 收入行，按收益从多到少。没上架的平台（0 首）不显示 —— 空行没有信息。 */
const revenueRows = computed(() =>
  Object.entries(eco.value?.revenue || {})
    .map(([key, v]) => ({ key, ...v }))
    .filter((r) => r.songs > 0)
    .sort((a, b) => b.earned_cny - a.earned_cny));

const providerLabel = (key: string) =>
  eco.value?.pricing.providers[key]?.label || key;

/**
 * 失败提示的措辞要看这个 provider 实际有没有产生消耗。
 *
 * 按积分计费的上游（Suno / 中台）失败也扣分；而 LLM 网关返回 503 时根本没扣。
 * 一律写「照样扣费」会把「上游挂了」误导成「你亏钱了」—— 两者要采取的行动
 * 完全不同：前者是等上游恢复，后者是查为什么在烧钱。
 * （同一处措辞在 cli/commands/stats.py 里也有，改一处要两处一起改。）
 */
const failedNote = (p: ProviderUsage) =>
  ((p.credits || 0) > 0 ? '（照样扣了积分）' : '（未产生消耗，多半是上游不可用）');

/** 量的单位跟着 provider 走：TTS 是秒、Suno 是次、LLM 是 token。 */
const fmtQty = (p: ProviderUsage) => {
  const unit = eco.value?.pricing.providers[p.provider]?.unit || '';
  if (unit === 'seconds') return `${Math.round(p.qty)} 秒音频`;
  if (unit === 'credits' && p.credits) return `${Math.round(p.credits)} 积分`;
  return `${Math.round(p.qty)} 次`;
};

/** 条形宽度按最贵的那项归一化 —— 绝对值差几个数量级时，等比条什么也看不出来。 */
const barWidth = (cost: number) => {
  const max = Math.max(...(eco.value?.summary.by_provider || []).map((p) => p.cost_cny || 0), 0.0001);
  return `${Math.max(2, ((cost || 0) / max) * 100)}%`;
};

const checkClass = (c: { ok: boolean; warn?: boolean }) =>
  (!c.ok ? 'is-bad' : c.warn ? 'is-warn' : 'is-ok');

/** 日志行里除固定字段外的部分，拼成一行紧凑文本。 */
const rest = (l: LogRecord) => Object.entries(l)
  .filter(([k]) => !['ts', 'level', 'event'].includes(k))
  .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
  .join('  ');

const loadLogs = async () => {
  try {
    logs.value = (await api.logs({ limit: 150, level: logLevel.value })).logs;
  } catch (e) { window.$message?.error(await toMessage(e)); }
};

const loadFast = async () => {
  // 两个接口互不依赖，并发拿 —— 串行只是白等一个往返。
  // 任一失败不影响另一个：allSettled 而不是 all。
  const [h, m] = await Promise.allSettled([api.health(), api.metrics()]);
  if (h.status === 'fulfilled') health.value = h.value;
  if (m.status === 'fulfilled') metrics.value = m.value;
};

const loadSlow = async () => {
  try { eco.value = await api.economics(days); } catch { /* 成本读不到不该打断整屏 */ }
};

const refresh = () => { loadFast(); loadSlow(); loadLogs(); };

let fastTimer = 0;
let slowTimer = 0;
onMounted(() => {
  refresh();
  fastTimer = window.setInterval(loadFast, 15_000);
  slowTimer = window.setInterval(loadSlow, 60_000);
});
onUnmounted(() => { clearInterval(fastTimer); clearInterval(slowTimer); });
</script>

<style scoped>
/* ── KPI 行 ── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--vf-space-3);
}
.kpi {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-4) var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kpi-label { font-size: 11px; color: var(--vf-text-3); letter-spacing: 0.04em; }
.kpi-value {
  font-size: 26px;
  font-weight: 600;
  color: var(--vf-text-1);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.kpi-value-sm { font-size: 17px; display: flex; align-items: center; gap: 8px; }
.kpi-sub { font-size: 11px; color: var(--vf-text-3); }
.kpi-saved .kpi-value { color: var(--vf-ok); }
.kpi-cost .kpi-value { color: var(--vf-text-1); }

.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--vf-text-4); flex: none; }
.kpi-health-ok .dot { background: var(--vf-ok); box-shadow: 0 0 8px var(--vf-ok); }
.kpi-health-degraded .dot { background: var(--vf-warn); box-shadow: 0 0 8px var(--vf-warn); }
.kpi-health-down .dot { background: var(--vf-err); box-shadow: 0 0 8px var(--vf-err); }
.kpi-health-degraded { border-color: var(--vf-warn-soft); }
.kpi-health-down { border-color: var(--vf-err-soft); }

/* ── 分区 ── */
.ops-tabs { margin-top: var(--vf-space-2); }
.pane-body { display: flex; flex-direction: column; gap: var(--vf-space-4); padding-top: var(--vf-space-3); }
.card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.section-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.title-hint { font-size: 11px; font-weight: 400; color: var(--vf-text-3); margin-left: auto; }
.empty { font-size: 12px; color: var(--vf-text-3); padding: var(--vf-space-4) 0; }
.foot-note { font-size: 11px; color: var(--vf-text-3); line-height: 1.7; margin: 0; }
.foot-note code {
  background: var(--vf-bg-3);
  padding: 1px 5px;
  border-radius: var(--vf-radius-xs);
  font-size: 10px;
}

/* ── 成本构成 ── */
.prov-list { display: flex; flex-direction: column; gap: var(--vf-space-4); }
.prov-row { display: flex; flex-direction: column; gap: 6px; }
.prov-head { display: flex; justify-content: space-between; align-items: baseline; }
.prov-name { font-size: 13px; color: var(--vf-text-1); }
.prov-cost { font-size: 14px; font-weight: 600; color: var(--vf-text-1); font-variant-numeric: tabular-nums; }
.prov-cost.free { color: var(--vf-ok); font-size: 12px; }
.prov-bar { height: 5px; background: var(--vf-bg-4); border-radius: var(--vf-radius-full); overflow: hidden; }
.prov-bar-fill {
  height: 100%;
  background: var(--vf-primary);
  border-radius: var(--vf-radius-full);
  transition: width 0.3s var(--vf-ease);
}
.prov-meta { font-size: 11px; color: var(--vf-text-3); }
.err-text { color: var(--vf-err); }
.warn-text { color: var(--vf-warn); }
.ok-text { color: var(--vf-ok); }

.est-tag {
  background: var(--vf-bg-4);
  color: var(--vf-text-3);
  padding: 0 6px;
  border-radius: var(--vf-radius-full);
  font-size: 10px;
}

/* ── 收入 ── */
.kpi-earn .kpi-value { color: var(--vf-ok); }
.rev-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--vf-space-3);
}
.rev-card {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  padding: var(--vf-space-3) var(--vf-space-4);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rev-head { display: flex; justify-content: space-between; align-items: center; gap: var(--vf-space-2); }
.rev-name {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--vf-text-1);
}
.rev-artist { font-size: 12px; color: var(--vf-text-2); }
.rev-earn { font-size: 16px; font-weight: 600; color: var(--vf-ok); font-variant-numeric: tabular-nums; }
.rev-stats { display: flex; gap: 10px; flex-wrap: wrap; font-size: 11px; color: var(--vf-text-3); }
.rev-rate { font-size: 12px; color: var(--vf-text-2); font-variant-numeric: tabular-nums; }
.rev-rate .src {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--vf-radius-full);
  margin-left: 4px;
}
.rev-rate .src.measured { background: var(--vf-ok-soft); color: var(--vf-ok); }
.rev-rate .src.configured { background: var(--vf-bg-4); color: var(--vf-text-3); }
.rev-7d { font-size: 11px; color: var(--vf-text-3); }

/* ── 表格 ── */
.table-scroll { overflow-x: auto; }
.cost-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cost-table th {
  text-align: left;
  font-weight: 500;
  color: var(--vf-text-3);
  font-size: 11px;
  padding: 6px 10px 6px 0;
  border-bottom: 1px solid var(--vf-border);
  white-space: nowrap;
}
.cost-table td {
  padding: 8px 10px 8px 0;
  border-bottom: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  vertical-align: top;
}
.cost-table .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.cost-table .strong { color: var(--vf-text-1); font-weight: 600; }
.cost-table .ttl { color: var(--vf-text-1); max-width: 220px; }
.cost-table .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.mix { display: flex; flex-wrap: wrap; gap: 4px; }
.mix-chip {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-full);
  padding: 1px 8px;
  font-size: 10px;
  color: var(--vf-text-3);
  white-space: nowrap;
}

/* ── 体检项 ── */
.check-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--vf-space-3);
}
.check {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-left: 2px solid var(--vf-text-4);
  border-radius: var(--vf-radius-sm);
  padding: var(--vf-space-3) var(--vf-space-4);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.check.is-ok { border-left-color: var(--vf-ok); }
.check.is-warn { border-left-color: var(--vf-warn); }
.check.is-bad { border-left-color: var(--vf-err); background: var(--vf-err-soft); }
.check-head { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--vf-text-1); }
.check.is-ok .check-head { color: var(--vf-text-1); }
.check.is-warn .check-head { color: var(--vf-warn); }
.check.is-bad .check-head { color: var(--vf-err); }
.check-detail { font-size: 11px; color: var(--vf-text-3); }

.ghost-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: transparent;
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.ghost-btn:hover { border-color: var(--vf-border-strong); color: var(--vf-text-1); }

/* ── 日志 ── */
.log-list {
  display: flex;
  flex-direction: column;
  max-height: 460px;
  overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
}
.log-row {
  display: flex;
  gap: 10px;
  padding: 5px 8px;
  border-bottom: 1px solid var(--vf-border);
  border-left: 2px solid transparent;
  align-items: baseline;
}
.log-row.lv-warn { border-left-color: var(--vf-warn); }
.log-row.lv-error { border-left-color: var(--vf-err); background: var(--vf-err-soft); }
.log-ts { color: var(--vf-text-4); flex: none; }
.log-event { color: var(--vf-text-1); flex: none; min-width: 110px; }
.log-rest { color: var(--vf-text-3); word-break: break-all; }
</style>
