import { useCallback, useEffect, useRef, useState } from 'react'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import { useAuth } from '@/features/auth/useAuth'
import {
  CHIME_BILL,
  CHIME_NEW_ORDER,
  CHIME_READY,
  CHIME_WAITER,
  playChime,
  primeNotificationAudio,
  unlockAudioNow,
} from './notificationSound'
import {
  primeNotificationPermission,
  requestNotificationPermissionNow,
  showStaffNotification,
} from './notify'
import type { RealtimeEvent } from '@/types'

const PREF_KEY = 'staff_alerts_enabled'

function loadEnabled(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) !== 'false' // default ON
  } catch {
    return true
  }
}

/** Render `#12` from an unknown event field, or '' if not a number/string. */
function orderLabel(v: unknown): string {
  return typeof v === 'number' || typeof v === 'string' ? `#${v}` : ''
}

export interface StaffToast {
  id: string
  text: string
}

function newId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}

/**
 * Single role-aware staff alert listener — mounted once in StaffLayout. Plays a
 * distinct chime (3×, auto-stopping) plus an OS notification for the events that
 * matter to the current role:
 *   KITCHEN  → new order placed (order.created)
 *   WAITER   → new order placed (order.created) + item ready to serve
 *              (order_item.status_changed → READY) + waiter called + bill requested
 *   COUNTER  → bill requested
 * Returns the on/off state + a toggle that unlocks audio and requests permission.
 */
export function useStaffAlerts(): {
  enabled: boolean
  toggle: () => void
  toasts: StaffToast[]
  dismissToast: (id: string) => void
} {
  const { role } = useAuth()
  const [enabled, setEnabled] = useState(loadEnabled)
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const roleRef = useRef(role)
  roleRef.current = role

  const [toasts, setToasts] = useState<StaffToast[]>([])
  const pushToast = useCallback((text: string) => {
    const id = newId()
    setToasts((cur) => [...cur, { id, text }])
    setTimeout(() => setToasts((cur) => cur.filter((t) => t.id !== id)), 8000)
  }, [])
  const dismissToast = useCallback(
    (id: string) => setToasts((cur) => cur.filter((t) => t.id !== id)),
    [],
  )

  // Prime audio + notification permission on the first incidental gesture.
  useEffect(() => {
    const cleanupAudio = primeNotificationAudio()
    const cleanupPerm = primeNotificationPermission()
    return () => {
      cleanupAudio()
      cleanupPerm()
    }
  }, [])

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev
      try {
        localStorage.setItem(PREF_KEY, String(next))
      } catch {
        /* ignore */
      }
      if (next) {
        // This runs inside the click handler → a valid user gesture.
        unlockAudioNow()
        requestNotificationPermissionNow()
      }
      return next
    })
  }, [])

  useStaffRealtime((event: RealtimeEvent) => {
    const r = roleRef.current
    const isKitchen = r === 'KITCHEN' || r === 'ADMIN'
    const isWaiter = r === 'WAITER' || r === 'ADMIN'
    const isCounter = r === 'COUNTER' || r === 'ADMIN'

    // Visible in-dashboard toast for a waiter call — shows even if sound is muted.
    if (isWaiter && event.type === 'waiter.called') {
      const table = typeof event['table_name'] === 'string' ? event['table_name'] : undefined
      pushToast(table ? `Table ${table} requests waiter` : 'A table requests waiter')
    }

    if (!enabledRef.current) return

    if (isWaiter && event.type === 'waiter.called') {
      const table = typeof event['table_name'] === 'string' ? event['table_name'] : undefined
      playChime(CHIME_WAITER)
      showStaffNotification({
        title: 'Waiter requested',
        body: table ? `Table ${table} requests waiter.` : 'A table requests a waiter.',
        tag: 'waiter-called',
      })
      return
    }

    if ((isKitchen || isWaiter) && event.type === 'order.created') {
      const count = event['item_count']
      const items = typeof count === 'number' ? ` · ${count} item${count !== 1 ? 's' : ''}` : ''
      playChime(CHIME_NEW_ORDER)
      showStaffNotification({
        title: 'New order',
        body: `New order ${orderLabel(event['order_number'])}${items}`.trim(),
        tag: 'new-order',
      })
      return
    }

    // Approval-gated batch: waiters get this INSTEAD of order.created — same
    // urgency as a new order, but it needs an approve/reject decision.
    if (isWaiter && event.type === 'order.approval_requested') {
      const table = typeof event['table_name'] === 'string' ? event['table_name'] : undefined
      playChime(CHIME_NEW_ORDER)
      showStaffNotification({
        title: 'Order awaiting approval',
        body: `${table ? `Table ${table}` : 'A table'} placed order ${orderLabel(event['order_number'])} — approve or reject it.`.trim(),
        tag: 'order-approval',
      })
      return
    }

    if (
      isWaiter &&
      event.type === 'order_item.status_changed' &&
      event['new_status'] === 'READY'
    ) {
      const product = typeof event['product_name'] === 'string' ? event['product_name'] : ''
      playChime(CHIME_READY)
      showStaffNotification({
        title: 'Ready to serve',
        body: product ? `Ready: ${product}` : 'An item is ready to serve.',
        tag: 'item-ready',
      })
      return
    }

    if ((isCounter || isWaiter) && event.type === 'bill.requested') {
      const table = typeof event['table_name'] === 'string' ? event['table_name'] : undefined
      const order = orderLabel(event['order_number'])
      playChime(CHIME_BILL)
      showStaffNotification({
        title: 'Bill requested',
        body: `${table ? `Table ${table}` : 'A table'} requested the bill${order ? ` (order ${order})` : ''}.`,
        tag: 'bill-requested',
      })
    }
  })

  return { enabled, toggle, toasts, dismissToast }
}
