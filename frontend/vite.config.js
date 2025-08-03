import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 8081,
    host: 'localhost',
    open: false,
    hmr: {
      overlay: false,
      port: 24678
    },
    watch: {
      usePolling: true,
      interval: 2000,
      ignored: ['**/node_modules/**', '**/dist/**', '**/.git/**']
    }
  },
  build: {
    outDir: 'dist'
  },
  optimizeDeps: {
    include: ['vue', 'element-plus', 'socket.io-client']
  }
})