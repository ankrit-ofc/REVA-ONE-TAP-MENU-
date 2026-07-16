/**
 * Customer session gate.
 *
 * Customer routes need a valid table session (X-Session-Token). That token is
 * kept in memory only, so a page reload wipes it. This guard prevents the
 * customer pages from firing API calls without a session (which would 401), and
 * transparently restores the session from the stored public QR token:
 *
 *  - hasSession            → render the customer pages.
 *  - no session, has QR    → re-run POST /scan to restore, showing a loader.
 *    token                   (create_or_reuse_session is idempotent, so this
 *                             returns the same active session.)
 *  - no session, no QR     → ask the diner to scan the QR on their table.
 *    token
 *
 * If the restaurant requires location, the restore goes through the same
 * geofence handshake as the initial scan; a location/too-far failure shows a
 * retry screen instead of silently dropping the diner.
 *
 * This is a UX boundary only — the backend enforces the session on every request.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useSession } from '@/features/session/useSession'
import { useScanMutation } from '@/features/session/sessionApi'
import { scanWithGeofence } from '@/features/session/geofenceScan'
import { GeolocationError } from '@/lib/geolocation'
import { setSessionToken } from '@/services/api'
import { getStoredQrToken, clearStoredQrToken, getSessionEnded } from '@/features/session/qrStorage'
import SessionEndedScreen from '@/pages/customer/SessionEndedScreen'
import Loader from '@/components/common/Loader'
import styles from '@/pages/customer/Scan.module.css'

type RestoreState =
  | { phase: 'restoring' }
  | { phase: 'noQr' }
  | { phase: 'location'; message: string } // location/too-far — QR kept, retryable

export default function RequireSession() {
  const { hasSession } = useSession()
  const [scan] = useScanMutation()
  const [state, setState] = useState<RestoreState>({ phase: 'restoring' })
  const attempted = useRef(false)
  const ended = getSessionEnded()

  const restore = useCallback(async () => {
    const qrToken = getStoredQrToken()
    if (!qrToken) {
      setState({ phase: 'noQr' })
      return
    }
    setState({ phase: 'restoring' })
    try {
      const data = await scanWithGeofence(scan, qrToken)
      // onQueryStarted populates the in-memory token + Redux session, but set it
      // here too so it is in place the instant we re-render.
      setSessionToken(data.session_token)
    } catch (err) {
      const status = (err as { status?: number }).status
      if (err instanceof GeolocationError || status === 403 || status === 428) {
        const detail = (err as { data?: { detail?: string } }).data?.detail
        setState({
          phase: 'location',
          message:
            status === 403
              ? detail ?? 'You must be at the restaurant to continue.'
              : 'This restaurant requires your location to order. Please enable location and try again.',
        })
        return
      }
      // Stored QR token is invalid/expired — drop it and ask to re-scan.
      clearStoredQrToken()
      setState({ phase: 'noQr' })
    }
  }, [scan])

  useEffect(() => {
    if (hasSession || attempted.current) return
    attempted.current = true

    // The session was terminated (e.g. paid) — do NOT silently re-scan into a new
    // one; the terminal screen below handles this. Only a real QR re-scan resets it.
    if (getSessionEnded()) return

    void restore()
  }, [hasSession, restore])

  if (hasSession) return <Outlet />

  // Session ended (paid): hard dead-end. Survives refresh/back/manual nav because
  // the marker lives in sessionStorage and we never auto re-scan above.
  if (ended) return <SessionEndedScreen info={ended} />

  if (state.phase === 'location') {
    return (
      <div className={styles.errorPage}>
        <div className={styles.errorBox}>
          <span className={styles.icon}>📍</span>
          <h1 className={styles.title}>Location needed</h1>
          <p className={styles.message}>{state.message}</p>
          <button className={styles.retryBtn} onClick={() => void restore()}>
            Try again
          </button>
        </div>
      </div>
    )
  }

  if (state.phase === 'noQr') {
    return (
      <div className={styles.errorPage}>
        <div className={styles.errorBox}>
          <span className={styles.icon}>📷</span>
          <h1 className={styles.title}>Scan to Order</h1>
          <p className={styles.message}>
            Please scan the QR code on your table to view the menu and place an order.
          </p>
        </div>
      </div>
    )
  }

  return <Loader fullscreen message="Restoring your session…" />
}
