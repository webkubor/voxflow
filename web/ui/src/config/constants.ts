/**
 * 配置常量层 —— 端口、轮询间隔、超时这些数字只在这里定义一次。
 *
 * 以前散在各处：api 层超时 20 秒、任务轮询 5 秒/忙时 1.5 秒、Suno 任务
 * 轮询 5 秒、看板轮询 4 秒 —— 要调节奏得全局搜数字，漏一处就是「有的
 * 地方快有的地方慢」。
 */
export const API_TIMEOUT_MS = 20_000;      // 本地服务请求超时：比这久基本是挂了
export const API_RETRY_LIMIT = 2;          // GET 重试次数（幂等才重试）

export const TASKS_POLL_MS = 5_000;        // 任务队列轮询间隔
export const TASKS_POLL_BUSY_MS = 1_500;   // 有任务在跑时的轮询间隔（更密）
export const SUNO_TASK_POLL_MS = 5_000;    // Suno 生成任务轮询间隔
export const BOARD_POLL_MS = 4_000;        // 看板轮询间隔（页面不可见时不轮询）
