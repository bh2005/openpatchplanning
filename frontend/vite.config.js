import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {                       // Entwicklung: API des lokal laufenden Backends (uvicorn auf :8000)
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
