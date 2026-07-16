/**
 * Persistence for the **public** QR token only.
 *
 * The QR token is the same signed string printed on the physical table placard
 * — it is not a secret bearer credential, so it is safe to keep in
 * sessionStorage. The live session/access tokens stay in memory only (Decision
 * D1). On a page reload the in-memory session is lost; the stored QR token lets
 * us transparently re-establish it via POST /scan (idempotent — see
 * create_or_reuse_session on the backend).
 */
const QR_TOKEN_KEY = 'qr_token'

export const getStoredQrToken = (): string | null => {
  try {
    return sessionStorage.getItem(QR_TOKEN_KEY)
  } catch {
    return null
  }
}

export const setStoredQrToken = (token: string): void => {
  try {
    sessionStorage.setItem(QR_TOKEN_KEY, token)
  } catch {
    // sessionStorage unavailable (private mode quota, etc.) — degrade silently;
    // the session still works for this page lifetime, just not across reloads.
  }
}

export const clearStoredQrToken = (): void => {
  try {
    sessionStorage.removeItem(QR_TOKEN_KEY)
  } catch {
    // ignore
  }
}

/**
 * "Session ended" marker.
 *
 * Set the instant a table's bill is paid (the backend has already invalidated
 * the session server-side). While this marker is present, RequireSession shows a
 * terminal "session ended — scan again" screen and never silently re-scans the
 * stored QR token into a fresh session. A genuine physical re-scan (Scan page)
 * clears it. Kept in sessionStorage so it survives a reload within the same tab.
 */
const SESSION_ENDED_KEY = 'qr_session_ended'

export interface SessionEndedInfo {
  invoiceNumber?: string
  total?: number
}

export const markSessionEnded = (info: SessionEndedInfo = {}): void => {
  try {
    sessionStorage.setItem(SESSION_ENDED_KEY, JSON.stringify(info))
  } catch {
    // ignore
  }
}

export const getSessionEnded = (): SessionEndedInfo | null => {
  try {
    const raw = sessionStorage.getItem(SESSION_ENDED_KEY)
    return raw ? (JSON.parse(raw) as SessionEndedInfo) : null
  } catch {
    return null
  }
}

export const clearSessionEnded = (): void => {
  try {
    sessionStorage.removeItem(SESSION_ENDED_KEY)
  } catch {
    // ignore
  }
}
