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

/** 平台标识。加平台时这里和 configs/platforms.json 一起改。 */
export type PlatformKey = 'qishui' | 'netease' | 'tencent';

/** 作品在某个平台上的状态。 */
export interface TrackPlatform {
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
  platforms: Record<PlatformKey, { label: string; cover: string; ai_field: string }>;
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
  synced_at: string;
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
}

export type CapabilitiesResponse = Record<'tts' | 'suno' | 'studio' | 'llm', Capability>;
