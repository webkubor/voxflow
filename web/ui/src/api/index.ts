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
 */

import ky, { HTTPError, TimeoutError } from 'ky';
import type {
  Album, CapabilitiesResponse, PersonasResponse, PipelineResponse,
  PlatformAccount, PlatformKey, Stage, Track,
} from '../types/api';

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
const http = ky.create({
  prefix: '/api',
  timeout: 20_000,
  retry: { limit: 2, methods: ['get'] },
});

/** 把 ky 的异常转成人能看懂的一句话。抛给调用方，由它决定怎么提示。 */
export async function toMessage(err: unknown): Promise<string> {
  if (err instanceof TimeoutError) return '请求超时，后端可能没在跑';
  if (err instanceof HTTPError) {
    try {
      const body = await err.response.json<{ detail?: string; error?: string }>();
      return body.detail || body.error || `HTTP ${err.response.status}`;
    } catch {
      return `HTTP ${err.response.status}`;
    }
  }
  return (err as Error)?.message || String(err);
}

const get = <T>(path: string, searchParams?: Record<string, string>) =>
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
  tasks: () => get<{ tasks: unknown[] }>('tasks'),
  cancelTask: (id: string) => del<{ ok: boolean }>(`tasks/${id}`),

  // ── 合成 ──
  clone: (body: unknown) => post<{ task_id: string }>('clone', body),
  design: (body: unknown) => post<{ task_id: string }>('design', body),
  dialogue: (body: unknown) => post<{ task_id: string }>('dialogue', body),

  // ── 文案 ──
  scripts: () => get<{ scripts: unknown[] }>('scripts'),
  saveScript: (body: unknown) => post<{ ok: boolean }>('scripts', body),
  deleteScript: (id: string) => del<{ ok: boolean }>(`scripts/${id}`),
  aiGenerate: (prompt: string) => post<{ text: string }>('llm/generate', { prompt }),
  aiPolish: (text: string) => post<{ text: string }>('llm/polish', { text }),
  aiLyrics: (body: unknown) => post<{ text: string; lyrics?: string }>('llm/lyrics', body),

  // ── 音频库 ──
  audioList: () => get<{ files: unknown[] }>('audio-list'),
  deleteAudio: (filename: string) => del<{ ok: boolean }>(`audio/${encodeURIComponent(filename)}`),

  // ── Suno ──
  sunoStatus: () => get<Record<string, unknown>>('suno/status'),
  sunoGenerate: (body: unknown) => post<{ task_id: string }>('suno/generate', body),

  // ── 下载接管 ──
  inbox: () => get<{ files: unknown[]; downloads_dir: string }>('inbox'),
  inboxImport: (paths: string[]) => post<{ ok: boolean; count: number }>('inbox/import', { paths }),
};

export type Api = typeof api;
