import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    // Accept any Host header so the app is reachable via a LAN IP or through the
    // Caddy HTTPS proxy (used for PWA testing on real devices), not just localhost.
    allowedHosts: true,
    // Proxy all API and WS paths to the backend dev server so the frontend
    // can make same-origin requests (avoids CORS issues in development).
    proxy: {
      '^/(auth|scan|session|menu|orders|kitchen|waiter|counter|invoices|webhooks|health|media|admin|superadmin)': {
        target: process.env.BACKEND_URL ?? 'http://localhost:8000',
        changeOrigin: true,
        // Browser page-navigation sends Accept: text/html — serve the SPA
        // instead of proxying, because routes like /scan and /menu exist on
        // both the frontend (React Router) and the backend (API endpoints).
        // JS fetch/XHR calls use application/json headers and get proxied.
        bypass(req) {
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
          return null
        },
      },
      '/ws': {
        target: (process.env.BACKEND_URL ?? 'http://localhost:8000').replace('http', 'ws'),
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
