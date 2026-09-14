/**
 * VoxError —— 统一的错误对象，把 HTTP 上下文 + 业务上下文 + 调用栈打包在一起。
 *
 * ## 为什么不用普通 Error
 *
 * ky 抛 HTTPError / TimeoutError，JS 抛 Error，但每个调用点只取 `.message`
 * 就丢了堆栈、URL、方法、状态码、响应体。35 credits 的 Suno 任务失败一次，
 * 用户只看到「HTTP 500」三秒 toast 就没了 —— 没法复现。
 *
 * VoxError 在 throw 时一次性把这些字段都打包，errorLog 直接序列化存，
 * 「复制错误详情」按钮可以一键贴到 issue 里。
 *
 * ## requestId
 *
 * 每次请求带一个 X-Request-ID，后端日志会回写。前端日志写 ID，
 * 跨前后端追问题不用猜。
 */
import { HTTPError, TimeoutError } from 'ky';

// vite.config.js 从 package.json 注入，见那里的 define。手抄一份的版本号
// 必然会过期，而它会跟着每个请求头发到后端，过期时比没有还糟。
export const CLIENT_VERSION = __APP_VERSION__;

/** 错误严重度 —— 影响 toast 时长和错误日志是否上报 */
export type ErrorSeverity = 'warning' | 'error' | 'fatal';

/** 错误来源：业务层错误 / 网络错误 / 后端错误 / 超时 / 未知 */
export type ErrorSource = 'validation' | 'network' | 'http' | 'timeout' | 'unknown';

/** 出错时正在做什么 —— 给用户和排错的人都看的场景标签 */
export interface ErrorContext {
  /** 业务动作的稳定 ID，例如 'synthesize.clone' / 'pipeline.advance' */
  action: string;
  /** 自由标签，比如 { persona: 'demo', textLength: 142 } —— 不含敏感数据 */
  tags?: Record<string, string | number | boolean>;
}

/** 错误日志条目（持久化形态） */
export interface ErrorRecord {
  id: string;
  timestamp: number;
  message: string;             // 给用户看的一句话
  detail: string;              // 完整 stack + 上下文字符串（复制用）
  severity: ErrorSeverity;
  source: ErrorSource;
  status?: number;             // HTTP status code
  method?: string;             // HTTP method
  url?: string;                // full URL
  requestId?: string;          // X-Request-ID
  context?: ErrorContext;
  fingerprint: string;         // 用于去重的 hash：message + status + url + action
  count: number;               // 同 fingerprint 出现的次数
}

export class VoxError extends Error {
  public readonly status?: number;
  public readonly method?: string;
  public readonly url?: string;
  public readonly requestId?: string;
  public readonly source: ErrorSource;
  public readonly context?: ErrorContext;
  public readonly severity: ErrorSeverity;
  public readonly cause?: unknown;

  constructor(params: {
    message: string;
    stack?: string;
    status?: number;
    method?: string;
    url?: string;
    requestId?: string;
    source?: ErrorSource;
    context?: ErrorContext;
    severity?: ErrorSeverity;
    cause?: unknown;
  }) {
    super(params.message);
    this.name = 'VoxError';
    this.status = params.status;
    this.method = params.method;
    this.url = params.url;
    this.requestId = params.requestId;
    this.source = params.source ?? 'unknown';
    this.context = params.context;
    this.severity = params.severity ?? 'error';
    this.cause = params.cause;
    if (params.stack) this.stack = params.stack;
  }

  /** 序列化成可读详情：栈 + 上下文字段，给「复制错误」按钮用 */
  toDetail(): string {
    const lines: string[] = [];
    lines.push(`VoxError: ${this.message}`);
    if (this.context?.action) lines.push(`  at: ${this.context.action}`);
    if (this.method || this.url) lines.push(`  ${this.method || '?'} ${this.url || '?'}`);
    if (this.status !== undefined) lines.push(`  status: ${this.status}`);
    if (this.requestId) lines.push(`  requestId: ${this.requestId}`);
    if (this.context?.tags) {
      const tagStr = Object.entries(this.context.tags)
        .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
        .join(' ');
      if (tagStr) lines.push(`  tags: ${tagStr}`);
    }
    if (this.cause instanceof Error && this.cause.message !== this.message) {
      lines.push(`  cause: ${this.cause.message}`);
    }
    if (this.stack) {
      lines.push('');
      lines.push(this.stack);
    }
    return lines.join('\n');
  }
}

/**
 * 把任意 thrown 值规整成 VoxError。
 *
 * 已知 ky 的两种异常结构（HTTPError / TimeoutError），其他按普通 Error 处理。
 * 调用方不再需要 try/catch 时判类型。
 */
export async function toError(
  err: unknown,
  context: ErrorContext,
  fallback: { method?: string; url?: string } = {},
): Promise<VoxError> {
  if (err instanceof VoxError) {
    // 已经包过的就把 context 补上（同一错误在不同调用点可能不同 action）
    if (!err.context) (err as { context?: ErrorContext }).context = context;
    return err;
  }

  if (err instanceof TimeoutError) {
    return new VoxError({
      message: '请求超时，后端可能没在跑',
      source: 'timeout',
      context,
      method: fallback.method,
      url: fallback.url,
      severity: 'error',
      cause: err,
    });
  }

  if (err instanceof HTTPError) {
    const { response } = err;
    let detail = '';
    try {
      const cloned = response.clone();
      const body = await cloned.json();
      const b = body as { detail?: string; error?: string };
      detail = b.detail || b.error || '';
    } catch {
      // body 不是 JSON
    }
    const msg = detail || `HTTP ${response.status}`;
    const requestId = response.headers.get('x-request-id') || undefined;
    const method = fallback.method || (response as unknown as { request?: { method?: string } }).request?.method;
    return new VoxError({
      message: msg,
      stack: err.stack,
      status: response.status,
      method,
      url: fallback.url || response.url,
      requestId,
      source: 'http',
      context,
      severity: response.status >= 500 ? 'fatal' : 'error',
      cause: err,
    });
  }

  if (err instanceof Error) {
    return new VoxError({
      message: err.message || String(err),
      stack: err.stack,
      source: 'unknown',
      context,
      method: fallback.method,
      url: fallback.url,
      severity: 'error',
      cause: err,
    });
  }

  return new VoxError({
    message: String(err),
    source: 'unknown',
    context,
    severity: 'error',
    cause: err,
  });
}

/** 兼容旧接口：把 thrown 值转成一句话字符串 */
export async function toMessage(err: unknown): Promise<string> {
  return (await toError(err, { action: 'unknown' })).message;
}

/**
 * 错误指纹 —— 同 action + status + url + 错误首句 视为同一错误，去重计数。
 * 不直接用 message 全句（带变量），只取前 80 字符 + 状态码指纹。
 */
export function fingerprintOf(err: VoxError): string {
  const head = err.message.slice(0, 80);
  return [err.context?.action ?? '', err.status ?? '', err.url ?? '', head].join('|');
}

/** 客户端日志前缀 —— 后端日志搜这个关键字能定位前端调用 */
export const LOG_PREFIX = '[VoxFlow]';
