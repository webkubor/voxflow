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
    emptyOutDir: false, // 设为 false 避免误删 static 目录下的其他非构建资产
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
