/*
 * Minimal, ONLINE-ONLY service worker.
 *
 * Its only jobs are (a) to satisfy PWA installability (a registered worker with a
 * fetch handler is required) and (b) to host notification handlers so OS-level
 * bill-request alerts can be shown via registration.showNotification().
 *
 * It deliberately caches NOTHING: every request goes to the network. This keeps a
 * live POS from ever serving stale menu/order/invoice/payment data, and means the
 * app simply doesn't work offline — by design. New deploys are picked up on reload.
 */

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

// Pass-through: never serve from cache. (Letting the request fall through to the
// network is enough; an explicit no-op handler keeps the app installable.)
self.addEventListener('fetch', () => {})

// Focus an existing window (or open one) when a notification is clicked.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) return client.focus()
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl)
      return undefined
    }),
  )
})
