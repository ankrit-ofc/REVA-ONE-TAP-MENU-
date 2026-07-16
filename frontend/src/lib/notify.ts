/*
 * OS-level notifications for staff alerts (Level 1: works while the app is open or
 * backgrounded). Prefers the service worker registration so the banner survives a
 * backgrounded tab, falling back to a page Notification. No dependencies.
 *
 * Permission must be requested from a user gesture, so primeNotificationPermission()
 * wires a one-time gesture listener (mirrors the audio-unlock approach).
 */

let primed = false

function notificationsSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

/**
 * Idempotently requests notification permission on the user's first interaction.
 * Returns a cleanup function that removes the pending listeners.
 */
export function primeNotificationPermission(): () => void {
  if (primed || !notificationsSupported()) return () => {}
  if (Notification.permission !== 'default') return () => {} // already granted/denied
  primed = true

  const ask = () => {
    void Notification.requestPermission().catch(() => {})
    remove()
  }
  const remove = () => {
    document.removeEventListener('pointerdown', ask)
    document.removeEventListener('keydown', ask)
  }

  document.addEventListener('pointerdown', ask, { once: true })
  document.addEventListener('keydown', ask, { once: true })
  return remove
}

/** Request notification permission immediately (from a user gesture, e.g. the toggle). */
export function requestNotificationPermissionNow(): void {
  if (!notificationsSupported()) return
  if (Notification.permission === 'default') void Notification.requestPermission().catch(() => {})
}

export interface StaffNotification {
  title: string
  body: string
  tag?: string
}

/**
 * Shows a staff OS notification (if permission was granted). No-ops when
 * unsupported or not granted — the audible chime still plays regardless.
 */
export function showStaffNotification({ title, body, tag }: StaffNotification): void {
  if (!notificationsSupported() || Notification.permission !== 'granted') return

  const options = {
    body,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: tag ?? 'staff-alert',
    data: { url: '/' },
  }

  // Prefer the service worker so the notification shows even when the tab is in
  // the background; fall back to a foreground Notification.
  if ('serviceWorker' in navigator) {
    void navigator.serviceWorker.ready
      .then((reg) => reg.showNotification(title, options))
      .catch(() => {
        try { new Notification(title, options) } catch { /* ignore */ }
      })
  } else {
    try { new Notification(title, options) } catch { /* ignore */ }
  }
}
