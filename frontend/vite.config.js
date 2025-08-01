import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 8081,
    host: 'localhost',
    open: false,
    hmr: {
      overlay: true  // 保持错误覆盖层，但可以设置为 false 来禁用
    },
    watch: {
      // 减少文件监听的敏感度，避免无限重启
      usePolling: false,
      interval: 1000,
      ignored: ['**/node_modules/**', '**/dist/**', '**/.git/**']
    }
  },
  build: {
    outDir: 'dist'
  },
  // 优化依赖预构建
  optimizeDeps: {
    include: ['vue', 'element-plus', 'socket.io-client']
  }
})