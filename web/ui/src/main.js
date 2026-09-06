import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router';
import './assets/main.css';

/**
 * naive-ui 的组件**不在这里注册** —— 交给 unplugin-vue-components 的
 * NaiveUiResolver 按模板自动解析（见 vite.config.js）。
 *
 * 这里以前是一份手工维护的 27 个组件清单。问题是加了新组件忘了补的话，
 * 那个标签会**静默不渲染**：不报错、不警告，页面上那块就是空的。
 * 今天栽了两次 —— 平台切换器和已上架表格都这么凭空消失过一次。
 *
 * 自动解析之后这类错误从根上不存在，而且 tree-shaking 只打包真正用到的。
 */
/**
 * 前端重新构建后，**已经开着的页面会挂** —— 自动刷一次救回来。
 *
 * ## 症状
 *
 * 页面看起来好好的，一点 tab 就变空白，而且**控制台可能什么都不报**。
 * 人的第一反应是「我的数据没了」——实际上数据一条没少，是这一页本身过期了。
 *
 * ## 为什么会这样
 *
 * 每个 tab 都是懒加载的（router 里的 `() => import(...)`），点的那一刻才去
 * 取对应的 chunk 文件。而 `vite build` 每次都会**清空 assets 目录**、按内容
 * 哈希生成新文件名 —— 于是老页面手里那个 chunk 名在服务器上已经不存在了，
 * 请求 404，动态 import 失败，那一屏就是空的。
 *
 * 首屏不会挂（它的 JS 早就下载完了），所以「打开正常、一点就黑」，
 * 看起来特别像数据丢了。
 *
 * ## 处理
 *
 * Vite 为这种情况提供了 `vite:preloadError` 事件。收到就重载一次 ——
 * 刷新后拿到的是新 index.html 和新 chunk 名，问题自然消失。
 *
 * **必须防重入，而且防重入本身很容易写错**。
 *
 * 第一版是「用一个布尔标记，导航成功就清掉」—— 实测**会无限刷新**：
 * 路由导航现在总是成功（见 router/index.ts 的占位组件），于是标记每次都被清，
 * 而 chunk 依然缺失 → 又 reload → 又清 → 死循环，`performance.now()` 一直
 * 停在几十毫秒。
 *
 * 现在用**时间窗口**：记下上次自救的时刻，10 秒内不再自救。
 *
 * - 版本过期（真实场景）：reload 一次拿到新 chunk，成功，之后再不触发；
 * - 文件真的没了 / 断网：reload 一次后进入冷却，把错误交给 MainLayout 的
 *   errorComponent 显示「刷新一下就好」，而不是把浏览器刷到死。
 *
 * 时间窗口比布尔值好的地方在于**它会自己过期**，不需要任何地方去清它 ——
 * 而「谁来清标记」正是上一版出错的地方。
 */
const RELOAD_AT = 'vf.preloadReloadAt';
const RELOAD_COOLDOWN_MS = 10_000;

window.addEventListener('vite:preloadError', (event) => {
  let last = 0;
  try { last = Number(sessionStorage.getItem(RELOAD_AT) || 0); } catch { /* 隐私模式 */ }
  if (Date.now() - last < RELOAD_COOLDOWN_MS) return;   // 冷却中：不是版本问题，别再刷
  try { sessionStorage.setItem(RELOAD_AT, String(Date.now())); } catch { /* 同上 */ }
  event.preventDefault();                                // 别让它冒泡成未捕获错误
  window.location.reload();
});

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount('#app');
