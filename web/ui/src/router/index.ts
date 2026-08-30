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
 *     ……
 *
 * 用 hash 模式（createWebHashHistory）而不是 history 模式：应用在
 * dev 下挂在 /static/、生产下挂在 / —— 两处 base 不同，history 模式
 * 的生产端要么 404 要么要改后端兜底；hash 不受 base 影响，两种环境
 * 都稳定，代价只是 URL 带个 #。
 */
import { createRouter, createWebHashHistory } from 'vue-router';

/** tab 名 → 路由。新增一屏 = 在这里加一条 + MainLayout 加 tab-pane。 */
export const tabRoutes = [
  { path: '/clone', name: 'clone', component: () => import('../tabs/CloneTab.vue') },
  { path: '/design', name: 'design', component: () => import('../tabs/DesignTab.vue') },
  { path: '/dialogue', name: 'dialogue', component: () => import('../tabs/DialogueTab.vue') },
  { path: '/suno', name: 'suno', component: () => import('../tabs/SunoTab.vue') },
  { path: '/works', name: 'works', component: () => import('../components/PipelineBoard.vue') },
  { path: '/publish', name: 'publish', component: () => import('../tabs/PublishTab.vue') },
  { path: '/library', name: 'library', component: () => import('../tabs/LibraryTab.vue') },
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
