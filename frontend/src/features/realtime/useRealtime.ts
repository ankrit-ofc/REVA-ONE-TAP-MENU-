import { useEffect, useRef } from 'react'
import { useDispatch } from 'react-redux'
import { ReconnectingWs } from './ws'
import type { AppDispatch } from '@/store/store'
import { useAuth } from '@/features/auth/useAuth'
import type { RealtimeEvent } from '@/types'

/**
 * Establishes an authenticated staff WebSocket.
 * Destroyed and recreated if authentication state changes.
 * Later phases attach cache-invalidation handlers via the onEvent prop.
 */
export function useStaffRealtime(
  onEvent?: (event: RealtimeEvent) => void,
): void {
  const { isAuthenticated } = useAuth()
  const dispatch = useDispatch<AppDispatch>()
  const wsRef = useRef<ReconnectingWs | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!isAuthenticated) return

    wsRef.current = new ReconnectingWs({
      mode: 'staff',
      onMessage(data) {
        const ev = data as RealtimeEvent
        if (ev?.type) {
          onEventRef.current?.(ev)
        }
      },
    })

    return () => {
      wsRef.current?.destroy()
      wsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, dispatch])
}

/**
 * Establishes an authenticated customer WebSocket.
 * Activated only when a table session is active.
 */
export function useCustomerRealtime(
  sessionToken: string | null,
  onEvent?: (event: RealtimeEvent) => void,
): void {
  const wsRef = useRef<ReconnectingWs | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!sessionToken) return

    wsRef.current = new ReconnectingWs({
      mode: 'customer',
      onMessage(data) {
        const ev = data as RealtimeEvent
        if (ev?.type) {
          onEventRef.current?.(ev)
        }
      },
    })

    return () => {
      wsRef.current?.destroy()
      wsRef.current = null
    }
  }, [sessionToken])
}
