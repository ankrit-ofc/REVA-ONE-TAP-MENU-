import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
      '^/(auth|scan|session|menu|orders|kitchen|waiter|counter|invoices|webhooks|health|media|admin|superadmin|dashboard)': {
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
      // /ar-banner is never a React route (unlike the shared prefixes above) —
      // it must always reach the backend, even for a real page navigation
      // (Accept: text/html), which is exactly how AR Quick Look's banner web
      // view loads it. So this gets its own rule with no bypass(), mirroring
      // prod's Caddyfile @always_api (unconditional) rather than @api.
      '^/ar-banner': {
        target: process.env.BACKEND_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: (process.env.BACKEND_URL ?? 'http://localhost:8000').replace('http', 'ws'),
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
