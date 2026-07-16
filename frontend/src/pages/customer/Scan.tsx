/**
 * Scan page — entry point after a customer scans a QR code.
 *
 * Expected URL: /scan?token=<qr_token>
 * The QR token is a signed server-issued opaque string; the client treats it
 * as a credential and passes it verbatim to POST /scan.
 *
 * If the restaurant requires location-based ordering, scanWithGeofence handles
 * the 428 handshake (request device location, retry). Location/too-far failures
 * surface a clear message with a "Try again" action.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useScanMutation } from '@/features/session/sessionApi'
import { scanWithGeofence } from '@/features/session/geofenceScan'
import { GeolocationError } from '@/lib/geolocation'
import { setStoredQrToken, clearSessionEnded } from '@/features/session/qrStorage'
import { setSessionToken } from '@/services/api'
import Loader from '@/components/common/Loader'
import styles from './Scan.module.css'

interface ScanError {
  title: string
  message: string
  canRetry: boolean
}

function describeError(err: unknown): ScanError {
  if (err instanceof GeolocationError) {
    if (err.kind === 'denied')
      return {
        title: 'Location needed',
        message:
          'This restaurant only takes orders from inside the venue. Please allow location access and try again.',
        canRetry: true,
      }
    if (err.kind === 'insecure')
      return {
        title: 'Location unavailable',
        message:
          'Sharing location needs a secure (https) connection. Please reopen the link over https and try again.',
        canRetry: true,
      }
    if (err.kind === 'unsupported')
      return {
        title: 'Location unavailable',
        message:
          "This device or browser can't share location, which this restaurant requires to order.",
        canRetry: false,
      }
    return {
      title: 'Couldn’t get your location',
      message:
        'We couldn’t determine your location. Make sure location is turned on, then try again.',
      canRetry: true,
    }
  }

  const status = (err as { status?: number }).status
  const detail = (err as { data?: { detail?: string } }).data?.detail
  if (status === 403)
    return {
      title: 'Too far from the restaurant',
      message: detail ?? 'You must be at the restaurant to start ordering.',
      canRetry: true,
    }
  if (status === 400)
    return {
      title: 'Invalid QR code',
      message: 'This QR code is invalid. Please scan the QR code on your table.',
      canRetry: false,
    }
  if (status === 404)
    return {
      title: 'Table not found',
      message: 'Table not found. Please ask a staff member for help.',
      canRetry: false,
    }
  return {
    title: 'Unable to connect',
    message: 'Something went wrong. Please try scanning again.',
    canRetry: true,
  }
}

export default function Scan() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [scan] = useScanMutation()
  const [error, setError] = useState<ScanError | null>(null)
  const [busy, setBusy] = useState(true)
  // Guard against React StrictMode double-invoking the effect in development.
  const didScan = useRef(false)

  const token = searchParams.get('token')

  const runScan = useCallback(async () => {
    if (!token) {
      setBusy(false)
      setError({
        title: 'QR code missing',
        message: 'QR code is missing or invalid. Please scan the QR code again.',
        canRetry: false,
      })
      return
    }
    setError(null)
    setBusy(true)
    // A real physical re-scan starts fresh — clear any "session ended" marker left
    // by a previous paid session so a new session can be established.
    clearSessionEnded()
    try {
      const data = await scanWithGeofence(scan, token)
      // Set the token synchronously before navigating so the first GET /menu
      // already has X-Session-Token. Persist the QR token for reload restore.
      setSessionToken(data.session_token)
      setStoredQrToken(token)
      navigate('/menu', { replace: true })
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }, [token, scan, navigate])

  useEffect(() => {
    if (didScan.current) return
    didScan.current = true
    void runScan()
  }, [runScan])

  if (error) {
    return (
      <div className={styles.errorPage}>
        <div className={styles.errorBox}>
          <span className={styles.icon}>📍</span>
          <h1 className={styles.title}>{error.title}</h1>
          <p className={styles.message}>{error.message}</p>
          {error.canRetry && (
            <button className={styles.retryBtn} onClick={() => void runScan()}>
              Try again
            </button>
          )}
        </div>
      </div>
    )
  }

  if (busy) return <Loader fullscreen message="Connecting to your table…" />

  return <Loader fullscreen message="Setting up your session…" />
}
