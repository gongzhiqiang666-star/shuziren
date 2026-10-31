import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8080' },
      '/output-api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8080' },
      '/healthz': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8080' },
    },
  },
  build: { sourcemap: false },
})
