/**
 * 后端 API 的返回结构 —— 前后端之间的契约。
 *
 * ## 为什么要这份文件
 *
 * 今天一天出的 bug 全是同一形态：**字段名/方法名对不上，但不报错**。
 *
 * - 组件读 `p.has_ref`，后端早改成了 `has_audio` → 标签永远显示「无样音」
 * - 组件判 `p.source === 'user'`，后端返回的是 `'registered'` → 删除按钮从没出现过
 * - `v-for="p in platforms"` 当数组遍历，后端给的是对象 → 复选框 value 是 undefined
 *
 * JS 里这些都是 `undefined`，静默地什么都不做。有了类型，它们在**编译时**就红。
 *
 * ## 维护约定
 *
 * 这份类型是**手写的**，不是从后端生成的 —— 后端是 Python，
 * 引一套 schema 生成链（OpenAPI → codegen）在这个规模上不值。
 *
 * 代价是它可能跟后端漂移。防线有两道：
 * 1. `scripts/smoke.py` 拿真实响应核对关键字段
 * 2. 改后端返回结构时，同步改这里 —— 就在同一个 PR 里
 */

/** 作品在流水线上的阶段。顺序即流程顺序。 */
export type Stage = 'draft' | 'generated' | 'selected' | 'publishing' | 'published' | 'archived';

/** 平台标识。加平台时这里和 configs/platforms.json、core/pipeline.PLATFORMS 一起改。 */
export type PlatformKey = 'qishui' | 'netease' | 'tencent';

/** 作品在某个平台上的一条上架记录。同一首原曲可以有多条（改名、拆分）。 */
export interface TrackPlatform {
  id?: number | null;
  platform?: string;
  /** 平台上的歌名，可以跟本地 title 不同。 */
  platform_title?: string;
  status: string;              // preparing | reviewing | online | rejected …
  song_id?: string | null;
  song_url?: string;
  album_id?: string | null;
  album?: string;
  album_url?: string;
  track_no?: number | null;
  duration?: number | null;    // 秒
  publish_date?: string;
  cover_url?: string;
  cover_local?: string;
  note?: string;
  submitted_at?: string;
  updated_at?: string;
  /** 发布配置。敏感字段（真实姓名等）在后端已脱敏，这里拿到的是打码版。 */
  config?: Record<string, unknown>;
}

/** 云备份状态，预留给 R2 同步。 */
export interface CloudBackup {
  status: string;
  label: string;
  location: string;
  updated_at: string;
}

export interface Track {
  id: string;
  title: string;
  stage: Stage;
  stage_label: string;
  stage_index: number;
  voice: string | null;
  clip_id: string | null;
  /** Suno 一次出两首，两个都留着 */
  clip_ids: string[];
  /** 平台状态是**对象**不是数组 —— 遍历要用 (值, 键) 两个形参 */
  platforms: Partial<Record<PlatformKey, TrackPlatform>>;
  /** 这个作品挂着的全部上架记录（含同一平台多条）。 */
  listings: TrackPlatform[];
  /** 有 Suno clip 或本地音频 = 原曲；否则是平台回填出来的孤儿。 */
  is_source: boolean;
  cloud_backup: CloudBackup;
  updated_at: string;
  note: string;
  // 创作元数据
  lyrics: string;
  tags: string;
  prompt: string;
  album_desc: string;
  audio_file: string;
  cover_file: string;
  /** 现成可用的 URL，前端不要自己拼路径 */
  cover_url: string;
  audio_url: string;
}

export interface PipelineResponse {
  stages: Stage[];
  stage_labels: Record<string, string>;
  /** 同样是对象不是数组 */
  platforms: Record<PlatformKey, {
    label: string;
    cover: string;
    ai_field: string;
    console?: string;
    color?: string;
  }>;
  summary: Record<string, number>;
  tracks: Track[];
}

export interface AlbumTrack {
  id: string;
  title: string;
  no: number | null;
  duration: number | null;
  url: string;
}

export interface Album {
  key: string;
  platform: string;
  album_id: string;
  title: string;
  track_count: number;
  publish_date: string;
  company: string;
  description: string;
  tags: string;
  cover_url: string;
  cover_local: string;
  url: string;
  synced_at: string;
  tracks: AlbumTrack[];
  /** 本地封面的访问地址，空串表示没有 */
  cover_api: string;
}

/** 平台后台指标。只有登录后才抓得到，抓不到时是空对象。 */
export interface PlatformStats {
  play_count?: string;
  fans?: string;
  works?: string;
  withdrawable_cny?: string;
  musician_index?: string;
  play_7d?: string;
  play_yesterday_delta?: string;
  roles?: string;
  synced_at?: string;
}

export interface PlatformAccount {
  platform: string;
  label: string;
  artist_id: string;
  artist_name: string;
  alias: string[];
  avatar_url: string;
  brief: string;
  /** 艺人主页 —— 发布表单填这个，平台据此核实音乐人身份 */
  artist_url: string;
  user_id: string;
  /** 个人主页 —— 听歌记录/动态，证明不了音乐人身份 */
  user_url: string;
  song_count: number;
  album_count: number;
  stats: PlatformStats;
  albums: Array<{ id: string; name: string; size: number }>;
  /** 台账里实际在线的数量。跟 song_count 对不上说明同步漏了。 */
  local_online_count: number;
  /** 台账里这个平台登记过的作品数（含审核中）。 */
  local_listed_count: number;
  synced_at: string;
  /** false = 还没跑过同步脚本，stats 是空的，不要当成「零播放」。 */
  synced: boolean;
  console_url: string;
  color: string;
}

/** GET /api/platform-accounts。accounts 始终包含三个平台。 */
export interface PlatformAccountsResponse {
  accounts: Record<string, PlatformAccount>;
  /** 发行主体艺名，来自 artist.json。各平台账号都归它。 */
  stage_name: string;
  roles: string[];
}

export interface Persona {
  name: string;
  /** 参考音频路径 —— 音频的唯一真源，**不要从 name 拼路径** */
  ref?: string;
  design?: string;
  instruction?: string;
  desc?: string;
  source?: string;
  /** has_temp / has_ref 是它的历史别名，都指同一个文件 */
  has_audio?: boolean;
}

export interface PersonasResponse {
  personas: Record<string, Persona>;
  presets: unknown[];
  total: number;
}

export interface Capability {
  ready: boolean;
  detail: string;
  credits?: number;
  plan?: string;
  identity?: string;
  model?: string;
  /** 月度总额 —— 后端没返回时不显示 X/Y 格式 */
  credits_total?: number;
  /** 下次续费日（ISO 字符串）—— 后端没返回时不显示「下次重置」 */
  renew_date?: string;
  /**
   * 这个主体受不受额度限制。自家租户不受限，此时**余额恒为 0 而功能完全正常** ——
   * 顶栏挂个「0 分」只会让人以为没额度了。判据要用它，不能只看 credits。
   */
  unmetered?: boolean;
}

export type CapabilitiesResponse = Record<'tts' | 'suno' | 'studio' | 'llm', Capability>;

// ── 可观测性与成本 ─────────────────────────────────────────
// 后端契约见 web/app.py 的 /api/health · /api/metrics · /api/logs · /api/economics。

/** 单项健康检查。ok=false 是坏了，ok=true+warn=true 是「还能用但要注意」。 */
export interface HealthCheck {
  ok: boolean;
  warn?: boolean;
  detail: string;
  [k: string]: unknown;
}

export interface HealthResponse {
  /** ok 全绿 · degraded 能用但有隐患 · down 有项目坏了 */
  status: 'ok' | 'degraded' | 'down';
  failed: string[];
  warned: string[];
  checks: Record<string, HealthCheck>;
  uptime_s: number;
}

export interface RouteMetric {
  key: string;
  n: number;
  errors: number;
  error_rate: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
}

export interface MetricsResponse {
  uptime_s: number;
  started_at: string;
  pid: number;
  routes: RouteMetric[];
  tasks: Record<string, number>;
  models_loaded: { base: boolean; design: boolean };
}

export interface LogRecord {
  ts: string;
  level: 'info' | 'warn' | 'error';
  event: string;
  [k: string]: unknown;
}

export interface ProviderUsage {
  provider: string;
  n: number;
  /** 业务量：秒 / 次 / 张，单位见 pricing.providers[x].unit */
  qty: number;
  /** 只统计成功调用的量 —— 「省下多少」按它算，失败的不能算成收益 */
  qty_ok: number;
  credits: number;
  cost_cny: number;
  /** 该 provider 成本里的估算部分 */
  estimated_cny: number;
  failed: number;
  /** 同样的量在商业 API 上要花多少（没有对标价的 provider 为 0） */
  market_cny: number;
  /** market_cny − cost_cny，本地跑省下的钱 */
  saved_cny: number;
}

export interface TrackEconomics {
  track_id: string;
  title: string;
  stage: string;
  cost_cny: number;
  by_provider: Record<string, { credits: number; cost_cny: number; n: number }>;
  /** 近 30 日播放量（音乐人后台）。null = 还没抓过，不是 0 —— 两者含义完全不同 */
  plays: number | null;
  /** 按实测千播单价折算的收益（不是平台实付，界面要标出来）。null 同上 */
  earned_cny: number | null;
  /** 折算收益 ÷ 成本。null = 缺收入数据或成本为 0 */
  roi: number | null;
  net_cny: number | null;
  /** 各平台按公开分成率算的回本播放数；0 = 该平台分成率未证实，算不了 */
  breakeven_plays: Record<string, number>;
}

/** 一个平台的收入侧实况。rate_source 说明千播单价是实测还是配置估算。 */
export interface PlatformRevenue {
  label: string;
  artist: string;
  songs: number;
  plays: number;
  earned_cny: number;
  cny_per_1k_plays: number;
  /** measured = 后台收益 ÷ 播放量反推（准）；configured = 公开资料估算 */
  rate_source: 'measured' | 'configured';
  plays_7d: number;
  fans: number;
  synced_at: string;
}

export interface EconomicsResponse {
  summary: {
    ok: boolean;
    days: number;
    total_cny: number;
    /** 全部 provider 省下的钱之和 —— 本地方案的价值，不算出来没人感知得到 */
    saved_cny: number;
    /** 总额里有多少来自 `voice backfill-costs` 的估算回填。不标出来，
     *  回填过一次之后就再也分不清哪些数字是实测的。 */
    estimated_cny: number;
    currency: string;
    by_provider: ProviderUsage[];
    by_day: { day: string; cost_cny: number; n: number }[];
    by_action: { provider: string; action: string; n: number; cost_cny: number }[];
  };
  revenue: Record<string, PlatformRevenue>;
  pnl: {
    /** 累计收益（平台后台的可提现金额） */
    lifetime_earned_cny: number;
    /** 有计量记录的作品的成本合计。注意与收益口径不同：收益是累计的，
     *  成本只覆盖接入计量之后的作品 —— 界面上必须写明，别当净利润用。 */
    lifetime_cost_cny: number;
    net_cny: number;
    total_plays: number;
    cny_per_1k_plays_measured: number;
  };
  avg_cost_per_track_cny: number;
  avg_breakeven_plays: number;
  tracks: TrackEconomics[];
  pricing: {
    providers: Record<string, {
      label: string; unit: string; cny_per_unit: number;
      market_cny_per_unit?: number; billing?: string; note?: string;
    }>;
    revenue: Record<string, { label: string; cny_per_1k_plays: number; confidence: string }>;
  };
  /** 有成本数据的作品数 / 台账总作品数。差额 = 接入计量前的历史作品。 */
  covered: number;
  total_tracks: number;
  /** 有单曲维度收入数据的作品数。0 = 还没跑过 scripts/ncm_track_stats.py */
  revenue_covered: number;
}
