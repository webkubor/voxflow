/**
 * 路由层 —— 每一屏一个 URL，刷新不丢屏、某一屏可以直接发链接。
 *
 * 以前靠 MainLayout 里 `currentTab` 一个变量切页：刷新回到默认页，
 * 想让人看「全网发行」得让人自己点过去。现在 tab 名即路由名：
 *
 *     /#/suno      AI 音乐
 *     /#/works     我的作品（流水线看板）
 *     /#/publish   全网发行
 *     /#/library   资产库
 *     /#/ops       运营台（成本 + 健康 + 日志）
 *     ……
 *
 * 用 hash 模式（createWebHashHistory）而不是 history 模式：应用在
 * dev 下挂在 /static/、生产下挂在 / —— 两处 base 不同，history 模式
 * 的生产端要么 404 要么要改后端兜底；hash 不受 base 影响，两种环境
 * 都稳定，代价只是 URL 带个 #。
 */
import { createRouter, createWebHashHistory } from 'vue-router';

/**
 * 每一屏用**占位组件**，不在这里动态 import。
 *
 * 这个应用没有 `<router-view>` —— 所有屏由 MainLayout 的 n-tabs 渲染，
 * router 只负责「URL ↔ 当前 tab」的同步。所以路由上挂的组件**不会被渲染**。
 *
 * 但 vue-router 仍然会**真的去执行** `() => import(...)`（它要解析组件才能
 * 完成导航）。于是原来那份写法有两个后果：
 *
 * 1. 每个 chunk 白加载一次 —— 加载完没人用。
 * 2. **更糟**：chunk 取不到时（前端重新构建过、老页面手里的文件名已失效），
 *    导航直接中止、URL 都不变，MainLayout 那套错误兜底根本没机会显示 ——
 *    表现就是「点了没反应 / 一片空白」，而且很像「数据没了」。
 *
 * 换成占位组件后，导航永远成功；真正的加载与失败兜底都交给 MainLayout 的
 * `defineAsyncComponent`（它有 errorComponent，会告诉人「刷新一下就好」）。
 */
const TabPlaceholder = { name: 'TabPlaceholder', render: () => null };

/** tab 名 → 路由。新增一屏 = 在这里加一条 + MainLayout 加 tab-pane。 */
export const tabRoutes = [
  { path: '/clone', name: 'clone', component: TabPlaceholder },
  { path: '/design', name: 'design', component: TabPlaceholder },
  { path: '/dialogue', name: 'dialogue', component: TabPlaceholder },
  { path: '/suno', name: 'suno', component: TabPlaceholder },
  { path: '/works', name: 'works', component: TabPlaceholder },
  { path: '/publish', name: 'publish', component: TabPlaceholder },
  { path: '/library', name: 'library', component: TabPlaceholder },
  { path: '/ops', name: 'ops', component: TabPlaceholder },
];

/** 合法 tab 名集合 —— MainLayout 的 n-tabs 用这个校验路由名。 */
export const TAB_NAMES = new Set(tabRoutes.map((r) => r.name));

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/clone' },
    ...tabRoutes,
    { path: '/:pathMatch(.*)*', redirect: '/clone' },   // 未知路径回默认屏
  ],
});

/**
 * 首屏落点：**按现在能干什么决定，不写死 /clone**。
 *
 * 全新安装时 `/clone` 是一整屏死路 —— 空音色库、灰掉的合成按钮、一条让人
 * 回终端下 7 GB 模型的警告。而那时候 AI 音乐（Suno）是就绪的，作品看板和
 * 运营台也照常能用。把人扔在死路上，是最容易让他直接关掉的第一印象。
 *
 * 只对**默认落点**生效：
 *   · 只在没有 hash（用户是直接打开首页）时改道
 *   · 显式访问 /#/clone 一律尊重，老用户的书签和习惯不受影响
 *   · 查不到状态就按原样去 /clone，宁可回到旧行为也不要卡在白屏
 *
 * 这是一次性判断，不常驻 —— 模型下完之后重开就正常落在 /clone。
 */
let firstRunChecked = false;

router.beforeEach(async (to) => {
  if (firstRunChecked || to.name !== 'clone') return true;
  firstRunChecked = true;
  // 用户显式打了 /#/clone 就别自作主张
  if (window.location.hash && window.location.hash !== '#/') return true;
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return true;
    const st = await res.json();
    if (st.base_model) return true;                 // 模型在，正常落 clone
    return { name: 'suno' };                        // 模型没下 → 落到能立刻用的那屏
  } catch {
    return true;                                    // 查不到就按原样走
  }
});
