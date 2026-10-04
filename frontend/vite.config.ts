import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Pin the dev port so it never drifts to 5174/5175/... which also breaks
    // the backend CORS allow-list. strictPort fails loudly instead of hopping.
    port: 5173,
    strictPort: true,
    // Bind to all interfaces so the server is reachable on localhost
    host: true,
  },
  preview: {
    port: 4173,
    strictPort: true,
  },
})