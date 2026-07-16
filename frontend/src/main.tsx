import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

const root = document.getElementById('root')
if (!root) throw new Error('#root element not found')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Register the online-only service worker (enables PWA install + OS notifications).
// It caches nothing, so the app stays online-only and never serves stale data.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Registration only works in a secure context (HTTPS or localhost); ignore otherwise.
    })
  })
}
