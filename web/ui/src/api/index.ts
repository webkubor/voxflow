/**
 * API 层 —— 所有后端请求的唯一出口。
 *
 * ## 为什么要收成一层
 *
 * 之前 25 处 `fetch` 散在 8 个文件里，每一处都自己写一遍：拼 URL、判
 * `res.ok`、解 JSON、抓错误、塞 store 的 error 字段。同一件事写 25 遍的后果：
 *
 * - **错误处理各不相同**。有的判 `!res.ok`，有的判 `data.ok === false`，
 *   有的两个都不判 —— 后端返回 500 时前端只是拿到 undefined 然后静默失败。
 * - **端点路径散落**。改一个路由要全局搜字符串，漏一处就是运行时 404。
 * - **没有类型**。每个调用点自己 `as any`，字段名对不对全靠记。
 *
 * 收进来之后：**端点在这里定义一次，返回类型标在函数签名上**，
 * 调用方只写 `api.pipeline()`，字段名错了编译期就红。
 *
 * ## 为什么用 ky 不用裸 fetch
 *
 * 裸 fetch 有两个坑，每个调用点都要自己踩一遍：
 * - **HTTP 错误不抛异常**。404/500 时 `fetch` 照样 resolve，
 *   要手动判 `res.ok` —— 忘了判就是拿着错误响应当正常数据用。
 * - 没有超时、没有重试。请求挂住时页面就一直转（今天刚踩过一次）。
 *
 * ky 把这些变成默认行为：非 2xx 直接抛、超时和重试是配置项。
 * 它只有 ~4KB，基于原生 fetch，不是 axios 那种自带一套 XHR 实现的重家伙。
 *
 * ## 请求头
 *
 * 每个请求自动带：
 *   X-Client-Version: 当前 package.json 版本
 *   X-Request-ID: 单次请求唯一 ID（前后端日志串联）
 *   X-Client-Tab: 当前路由名（多 tab 调试时区分）
 */

import ky, { HTTPError, TimeoutError } from 'ky';
import { API_TIMEOUT_MS, API_RETRY_LIMIT } from '../config/constants';
import type {
  Album, CapabilitiesResponse, PersonasResponse, PipelineResponse,
  EconomicsResponse, HealthResponse, LogRecord, MetricsResponse,
  PlatformAccount, PlatformKey, Stage, Track,
} from '../types/api';
import { CLIENT_VERSION, toError, toMessage, VoxError } from '../lib/errors';

export { toError, toMessage };
export type { ErrorContext, VoxError } from '../lib/errors';

/**
 * 统一实例。
 *
 * - `prefix: '/api'` —— 端点写 `pipeline` 而不是 `/api/pipeline`，
 *   前缀改了只动这一处。
 *   **必须带前导斜杠**：ky 是「把 prefix 和输入拼成字符串」再交给 fetch
 *   解析的，写 `'api'` 是相对路径，按页面地址解析 —— vite base 是
 *   `/static/`，dev 模式页面地址就是 `/static/`，于是所有请求都打到
 *   `/static/api/...` 然后 404，整页加载失败（能力/模型/音色库全挂）。
 *   带前导斜杠则永远按 origin 解析：dev（5173 代理到后端）和生产都正确。
 * - `timeout` 20 秒：本地服务，比这久基本就是挂了；无限等只会让页面一直转。
 * - `retry` 只对幂等方法生效（ky 默认不重试 POST），够用。
 */
let _currentTab = 'unknown';
export function setCurrentTab(tab: string): void {
  _currentTab = tab;
}

const http = ky.create({
  prefix: '/api',
  timeout: API_TIMEOUT_MS,
  retry: { limit: API_RETRY_LIMIT, methods: ['get'] },
  hooks: {
    // ky 2.x 的 beforeRequest 收**一个 state 对象** `{ request, options }`，
    // 不是 1.x 的 `(input, options)` 两个参数，而且 headers 挂在 request 上
    // （options 上没有）。之前这里按 1.x 的形状写，还用 `as unknown as`
    // 把类型强转掉了 —— 于是升级到 2.x 后每个请求都在 hook 里抛
    // `Cannot read properties of undefined (reading 'headers')`，
    // **整个界面的接口全挂**，而编译期一声不吭。
    //
    // 教训：`as unknown as` 把类型检查关掉的地方，正是升级时最先坏、
    // 又最难发现的地方。这里不再强转，签名对不上就让它编译失败。
    beforeRequest: [
      ({ request }) => {
        request.headers.set('X-Client-Version', CLIENT_VERSION);
        request.headers.set('X-Client-Tab', _currentTab);
        if (!request.headers.has('X-Request-ID')) {
          request.headers.set('X-Request-ID', genRequestId());
        }
      },
    ],
  },
});

/** 8 字符 ID，足够在一次会话里唯一 */
function genRequestId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** 导出给单测用 */
export const __testing = { genRequestId };

// searchParams 放宽到 string | number | boolean —— ky 本来就接受这三种并各自
// 序列化。收窄成 string 只是逼调用方在每个数字参数上写 String()，
// 那既没有换来任何安全性，还容易漏一个就编译不过。
const get = <T>(path: string, searchParams?: Record<string, string | number | boolean>) =>
  http.get(path, searchParams ? { searchParams } : undefined).json<T>();
const post = <T>(path: string, json?: unknown) => http.post(path, { json }).json<T>();
const postForm = <T>(path: string, body: FormData) => http.post(path, { body }).json<T>();
const patchForm = <T>(path: string, body: FormData) => http.patch(path, { body }).json<T>();
const del = <T>(path: string) => http.delete(path).json<T>();

/**
 * 所有端点。**新增接口加在这里，不要在组件里直接写 fetch。**
 *
 * 路径不带前导斜杠 —— ky 的 prefixUrl 要求相对路径，写成 `/pipeline`
 * 会被当成绝对路径而绕过前缀（这是 ky 唯一反直觉的地方）。
 */
export const api = {
  // ── 作品流水线 ──
  pipeline: () => get<PipelineResponse>('pipeline'),
  setStage: (track_id: string, stage: Stage) => post('pipeline/stage', { track_id, stage }),
  upsertTrack: (track: Partial<Track> & { track_id: string }) => post('pipeline/track', track),
  setPlatformStatus: (p: { track_id: string; platform: PlatformKey; status: string }) =>
    post('pipeline/platform', p),

  // ── 艺人档案 ──
  // 注意：后端会把真实姓名这类字段脱敏后再返回（core/pipeline._redact），
  // 界面拿到的是打码版。要原值只能读 ~/.voxflow/configs/artist.json。
  artist: () => get<Record<string, unknown>>('artist'),
  saveArtist: (body: unknown) => post<{ ok: boolean; artist: Record<string, unknown> }>('artist', body),

  // ── 专辑与平台 ──
  albums: (platform?: string) =>
    get<{ albums: Record<string, Album> }>('albums', platform ? { platform } : undefined),
  platformAccounts: () => get<{ accounts: Record<string, PlatformAccount> }>('platform-accounts'),
  publishBoard: () => get<{ accounts: unknown[]; tracks: Track[] }>('publish-board'),

  // ── 音色 ──
  personas: () => get<PersonasResponse>('personas'),
  addPersona: (form: FormData) => postForm<{ ok: boolean; key: string }>('personas/add', form),
  updatePersona: (key: string, form: FormData) =>
    patchForm<{ ok: boolean; name: string; desc: string }>(`personas/${encodeURIComponent(key)}`, form),
  deletePersona: (key: string) => del<{ ok: boolean }>(`personas/${encodeURIComponent(key)}`),

  // ── 能力与状态 ──
  status: () => get<Record<string, unknown>>('status'),
  capabilities: () => get<CapabilitiesResponse>('capabilities'),
  llmStatus: () => get<{ available: boolean; model: string; error?: string }>('llm/status'),

  // ── 任务 ──
  tasks: () => get<{ tasks: { id: string; status: string; error?: string }[] }>('tasks'),
  cancelTask: (id: string) => del<{ ok: boolean }>(`tasks/${id}`),

  // ── 合成 ──
  clone: (body: unknown) => post<{ task_id: string }>('clone', body),
  design: (body: unknown) => post<{ task_id: string }>('design', body),
  dialogue: (body: unknown) => post<{ task_id: string }>('dialogue', body),

  // ── 文案 ──
  scripts: () => get<{ scripts: unknown[] }>('scripts'),
  // 后端 ScriptSaveRequest 的字段是 content/title（title 可空）。
  // 之前这里不收形参、字段发成 text，请求体对不上后端，422 被吞。
  saveScript: (p: { content: string; title?: string }) =>
    post<{ ok: boolean; scripts: unknown[] }>('scripts', p),
  deleteScript: (id: string) => del<{ ok: boolean }>(`scripts/${id}`),
  aiGenerate: (prompt: string) => post<{ text: string }>('llm/generate', { prompt }),
  // 后端 LLMPolishRequest / LLMLyricsRequest 都是 {text|prompt, style?}
  aiPolish: (p: { text: string; style?: string }) => post<{ text: string }>('llm/polish', p),
  aiLyrics: (p: { prompt: string; style?: string }) =>
    post<{ text: string; lyrics?: string }>('llm/lyrics', p),

  // ── 音频库 ──
  audioList: () => get<{ files: unknown[] }>('audio-list'),
  deleteAudio: (filename: string) => del<{ ok: boolean }>(`audio/${encodeURIComponent(filename)}`),

  // ── Suno ──
  sunoStatus: () => get<Record<string, unknown>>('suno/status'),
  sunoGenerate: (p: { title: string; tags?: string; lyrics?: string; persona?: string }) =>
    post<{ task_id: string }>('suno/generate', p),
  /**
   * 上传原曲音频做真「同曲不同演绎」 —— Suno covers API。
   *
   * 前端已经准备好 FormData / UI，但后端要实现：
   *   POST /api/suno/cover
   *   Content-Type: multipart/form-data
   *   fields: audio (file), title, tags, lyrics, persona
   *
   * 后端收到后转发给 Suno 的 /cover 端点（v3.5+），返回 task_id。
   * 没实现之前调用会 404，错误日志里能看到具体原因。
   */
  sunoCover: (form: FormData) => postForm<{ task_id: string }>('suno/cover', form),

  // ── 热点风格追踪（测试1：哪个火做哪个，不抄袭）──
  trending: () => get<{
    ok: boolean; updated?: string; error?: string;
    songs?: { rank: number; name: string; artist: string; score: number; platforms: string[] }[];
    trend?: {
      trend?: string; tags?: string; moods?: string[]; themes?: string[];
      hotness?: number; hotness_reason?: string;
    };
  }>('trending'),

  // ── 模型下载（首次运行）──
  modelDownloadStatus: () => get<{
    models: Record<string, {
      ready: boolean; running: boolean; downloading: boolean;
      percent: number; downloaded_mb: number; total_mb: number;
    }>;
    can_do_now: string[];
    needs_base: string[];
  }>('models/download'),
  startModelDownload: (model: 'Base' | 'VoiceDesign') => {
    // 后端收的是 Form（和其它几个上传类端点一致），不是 JSON
    const fd = new FormData();
    fd.append('model', model);
    return postForm<{ ok: boolean; status: string; detail: string }>('models/download', fd);
  },

  // ── 封面出图（museav 中台）──
  coverStatus: () => get<{
    available: boolean; can_generate: boolean; credits: number;
    /** 不受额度闸门约束（自家租户）。余额恒为 0 但出图正常，只看 credits 会误判 */
    unmetered: boolean;
    covers_left: number; credits_per_cover: number; est_cny: number; detail: string;
    /** 常用比例，给下拉填值用。**不是白名单** */
    common_ratios: { value: string; label: string }[];
    /** 目标短边（平台要求：汽水 ≥1440、网易云 ≥1400） */
    cover_side: number;
    /** 各常用比例算出的实际出图尺寸，如 { "1:1": "1440x1440" } */
    sizes: Record<string, string>;
  }>('cover/status'),
  generateCover: (p: {
    track_id: string; title: string; tags?: string; prompt?: string;
    /** 任意 W:H（1:1 / 3:4 / 1:2.1 …）。不限枚举 —— 中台支持任意尺寸，
     *  合法性由它判定；写错会在提交时 400 挡掉。 */
    ratio?: string;
    /** 显式尺寸 'WxH'。留空则按 ratio 自动算一个短边 ≥1440 的 */
    size?: string;
  }) => post<{ task_id: string }>('cover/generate', p),

  // ── 可观测性与成本 ──
  // 四个分开而不是合成一个 /debug：想看一眼健康状态时，不该等日志和
  // 聚合查询也跑完。前端也按这个粒度各自刷新（健康 10 秒、成本 60 秒）。
  health: () => get<HealthResponse>('health'),
  metrics: () => get<MetricsResponse>('metrics'),
  logs: (p?: { limit?: number; level?: string; event?: string; days?: number }) =>
    get<{ logs: LogRecord[] }>('logs', p),
  economics: (days = 30) => get<EconomicsResponse>('economics', { days }),

  // ── 下载接管 ──
  inbox: () => get<{ files: unknown[]; downloads_dir: string }>('inbox'),
  inboxImport: (paths: string[]) => post<{ ok: boolean; count: number }>('inbox/import', { paths }),
};

export type Api = typeof api;
