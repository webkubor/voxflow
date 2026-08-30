import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { agentEyes, agentProxy } from 'vite-plugin-agent-eyes';

// https://vite.dev/config/
export default defineConfig({
  // 把构建时间烧进产物 —— 页面上显示它，刷新后时间没变就说明没重新构建。
  // 之前没有这个，改了代码看不到效果时永远要先怀疑一遍「是不是没 build」。
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toLocaleString('zh-CN', { hour12: false })),
  },
  plugins: [
    vue(),
    // 运行时遥测：把控制台错误、网络请求、交互轨迹落成结构化日志（log/<port>/）。
    //
    // 装它的直接原因：今天一整天的 bug 都是「不报错但没生效」——
    // store 方法名拼错、字段名对不上、复选框 value 是 undefined。
    // 这些在浏览器控制台里转瞬即逝，我只能靠反复截图猜。
    // 有了落盘日志，可以直接读「刚才那次请求返回了什么、哪一行报了错」。
    agentEyes(),
  ],
  base: '/static/',
  resolve: {
    dedupe: ['vue']
  },
  build: {
    outDir: '../static',
    // 每次构建先清空。之前设 false 是怕误删 static 下的其它资产，但实际查过 ——
    // static/ 里只有 assets/ 和 index.html，两个都是构建产物，没有要保护的东西。
    // 不清的代价是每改一次堆一份带 hash 的新文件：实测堆到 15 个、9.4MB，
    // 而真正被引用的只有 2 个。
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // agentProxy 包一层：代理请求的实际 URL、状态码、Set-Cookie 都会落日志。
      // 原生 proxy 出问题时只有一句 500，看不到到底请求了什么。
      '/api': agentProxy('http://localhost:8866'),
    },
  },
});
