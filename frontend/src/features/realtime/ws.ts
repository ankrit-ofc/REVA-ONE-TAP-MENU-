/**
 * Authenticated WebSocket client with exponential-backoff reconnection.
 *
 * Security invariants:
 * - Long-lived credentials NEVER appear in the WS URL. Each connect attempt
 *   first POSTs to /auth/ws-ticket (staff) or /session/ws-ticket (customer) —
 *   authenticated via the normal header interceptors — and receives a
 *   short-lived single-use ticket, which is the only thing in the query string.
 * - restaurant_id / tenant scope comes from the server-side ticket, never from
 *   any channel name the client can choose.
 * - WS close code 1008 (Policy Violation) means the server rejected our
 *   credentials; we do NOT reconnect in that case.
 */
import { api, getAccessToken, getSessionToken } from '@/services/api'

export type WsMode = 'staff' | 'customer'
export type MessageHandler = (data: unknown) => void

export interface WsConfig {
  mode: WsMode
  onMessage: MessageHandler
  onOpen?: () => void
  onClose?: (wasClean: boolean) => void
}

const WS_POLICY_VIOLATION = 1008
const MAX_BACKOFF_MS = 30_000

// Keepalive: ping so the client→server leg stays active, and treat silence longer
// than STALE_MS as a dead (half-open) socket. The server heartbeats every ~25s, so
// a healthy connection is never stale; one dropped by a proxy (Cloudflare ~100s
// idle) is detected and re-established within ~STALE_MS instead of hanging silently.
const PING_INTERVAL_MS = 20_000
const STALE_MS = 45_000

/**
 * Fetch a fresh single-use ticket and build the WS URL.
 * Returns null when no credential is available yet (caller recreates later);
 * throws when the ticket request itself fails (caller retries with backoff).
 */
async function buildWsUrl(mode: WsMode): Promise<string | null> {
  const credential = mode === 'staff' ? getAccessToken() : getSessionToken()
  if (!credential) return null

  const endpoint = mode === 'staff' ? '/auth/ws-ticket' : '/session/ws-ticket'
  const response = await api.post(endpoint)
  const ticket: unknown = (response.data as { ticket?: unknown } | null)?.ticket
  if (typeof ticket !== 'string' || ticket.length === 0) {
    throw new Error('Malformed ws-ticket response')
  }

  const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
  const wsBase = apiBase
    ? apiBase.replace(/^http/, 'ws')
    : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  return `${wsBase}/ws/${mode}?ticket=${encodeURIComponent(ticket)}`
}

export class ReconnectingWs {
  private ws: WebSocket | null = null
  private destroyed = false
  private retryDelayMs = 1_000
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private lastActivity = 0

  constructor(private readonly config: WsConfig) {
    this.connect()
  }

  private connect(): void {
    if (this.destroyed) return
    void this.connectAsync()
  }

  private async connectAsync(): Promise<void> {
    let url: string | null
    try {
      url = await buildWsUrl(this.config.mode)
    } catch {
      // Ticket fetch failed (network / backend restart) — retry with backoff.
      this.scheduleReconnect()
      return
    }
    if (this.destroyed) return
    if (!url) return // credential not yet available; caller recreates when ready

    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.retryDelayMs = 1_000
      this.lastActivity = Date.now()
      this.startHeartbeat()
      this.config.onOpen?.()
    }

    this.ws.onmessage = (event: MessageEvent<string>) => {
      // Any frame (event OR server heartbeat) proves the socket is alive.
      this.lastActivity = Date.now()
      try {
        const data = JSON.parse(event.data) as unknown
        // Swallow keepalive frames; screens only care about domain events.
        if ((data as { type?: unknown } | null)?.type === 'heartbeat') return
        this.config.onMessage(data)
      } catch {
        // discard malformed frames
      }
    }

    this.ws.onclose = (event: CloseEvent) => {
      this.stopHeartbeat()
      this.config.onClose?.(event.wasClean)
      if (this.destroyed || event.code === WS_POLICY_VIOLATION) return
      this.scheduleReconnect()
    }

    this.ws.onerror = () => {
      // onclose fires after onerror; reconnect is handled there.
    }
  }

  /** Exponential-backoff reconnect (shared by onclose and ticket-fetch failures). */
  private scheduleReconnect(): void {
    if (this.destroyed) return
    this.retryTimer = setTimeout(() => {
      this.retryDelayMs = Math.min(this.retryDelayMs * 2, MAX_BACKOFF_MS)
      this.connect()
    }, this.retryDelayMs)
  }

  /** Ping periodically and force-reconnect a socket that has gone silent. */
  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.pingTimer = setInterval(() => {
      if (Date.now() - this.lastActivity > STALE_MS) {
        this.forceReconnect()
        return
      }
      try {
        this.ws?.send('ping')
      } catch {
        /* a failed send surfaces as onclose */
      }
    }, PING_INTERVAL_MS)
  }

  /**
   * Tear down a half-open socket and reconnect immediately. We detach the old
   * socket's handlers first so its (possibly delayed) onclose cannot also
   * schedule a backoff reconnect — exactly one reconnect happens.
   */
  private forceReconnect(): void {
    this.stopHeartbeat()
    const old = this.ws
    this.ws = null
    if (old) {
      old.onopen = null
      old.onmessage = null
      old.onclose = null
      old.onerror = null
      try {
        old.close()
      } catch {
        /* ignore */
      }
    }
    this.retryDelayMs = 1_000
    this.connect()
  }

  private stopHeartbeat(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }

  destroy(): void {
    this.destroyed = true
    if (this.retryTimer !== null) clearTimeout(this.retryTimer)
    this.stopHeartbeat()
    this.ws?.close()
  }
}
