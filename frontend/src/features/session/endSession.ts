/**
 * Hard-terminate the customer's table session on the client.
 *
 * The backend already invalidates the session server-side at payment; this clears
 * every client-side trace so the dead session can't be silently resurrected:
 *   - drops the in-memory session token,
 *   - clears the persisted QR token (so a reload won't auto re-scan), and
 *   - sets the "session ended" marker that makes RequireSession show the terminal
 *     "scan again" screen.
 * A genuine physical re-scan (Scan page) clears the marker and starts fresh.
 */
import { setSessionToken } from '@/services/api'
import { clearStoredQrToken, markSessionEnded, type SessionEndedInfo } from './qrStorage'
import { clearSession } from './sessionSlice'
import type { AppDispatch } from '@/store/store'

export function endCustomerSession(dispatch: AppDispatch, info?: SessionEndedInfo): void {
  setSessionToken(null)
  clearStoredQrToken()
  markSessionEnded(info)
  dispatch(clearSession())
}
