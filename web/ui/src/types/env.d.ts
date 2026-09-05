/**
 * 全局环境声明。
 *
 * ⚠️ 这个文件顶层有 `import`，所以它是**模块**而不是全局脚本 ——
 * 模块里的 `declare const` 只在本文件可见。凡是要全站可见的东西，
 * 都必须写在下面的 `declare global` 块里，写在外面等于没写
 * （编译期报 "Cannot find name"，而且只在真正用到它的那个文件里报，
 * 很容易被当成那个文件自己的问题）。
 */
import type { DialogApi, MessageApi } from 'naive-ui';

declare global {
  /** vite.config.js 里 define 进来的构建时间。页面角落显示它，一眼看出新旧。 */
  const __BUILD_TIME__: string;

  /** vite.config.js 从 package.json 注入的版本号，随请求头发到后端。 */
  const __APP_VERSION__: string;

  /**
   * MessageApi.vue 把 Naive UI 的 message/dialog 挂到了 window 上，
   * 这样非 setup 上下文（store、工具函数）里也能弹提示。
   *
   * 但运行时挂上去 ≠ TypeScript 知道 —— 声明缺了这一份，任何 .ts/.vue
   * 里写 window.$message 都是编译错误，于是只能到处 `as any` 绕过去。
   *
   * 标成可选：MessageApi 挂载之前（或组件树外）它确实是 undefined，
   * 声明成必有会让 `?.` 显得多余，而那个 `?.` 恰恰是必要的。
   */
  interface Window {
    $message?: MessageApi;
    $dialog?: DialogApi;
  }
}

export {};
