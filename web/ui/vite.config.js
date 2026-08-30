import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
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
      '/api': {
        target: 'http://localhost:8866',
        changeOrigin: true,
      },
    },
  },
});
