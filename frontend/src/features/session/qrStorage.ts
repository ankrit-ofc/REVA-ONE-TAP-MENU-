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

/**
 * "Receipt contact already captured" marker for the current visit.
 *
 * The contact form has two entry points (Request Bill, and the payment-received
 * screen) and must never be shown twice. A React state flag would not survive
 * the gateway redirect out to eSewa/Khalti and back, so the marker lives in
 * sessionStorage. Cleared by a genuine re-scan, exactly like the ended marker.
 */
const CONTACT_CAPTURED_KEY = 'qr_contact_captured'

export const markContactCaptured = (): void => {
  try {
    sessionStorage.setItem(CONTACT_CAPTURED_KEY, '1')
  } catch {
    // ignore
  }
}

export const isContactCaptured = (): boolean => {
  try {
    return sessionStorage.getItem(CONTACT_CAPTURED_KEY) === '1'
  } catch {
    return false
  }
}

export const clearContactCaptured = (): void => {
  try {
    sessionStorage.removeItem(CONTACT_CAPTURED_KEY)
  } catch {
    // ignore
  }
}

/**
 * "Scan popup already shown" marker for the current visit.
 *
 * The promotional popup must show at most once per table session — this
 * marker survives reload/navigation within the tab and is cleared by a
 * genuine re-scan, exactly like the contact-captured marker above.
 */
const POPUP_SEEN_KEY = 'qr_popup_seen'

export const markPopupSeen = (): void => {
  try {
    sessionStorage.setItem(POPUP_SEEN_KEY, '1')
  } catch {
    // ignore
  }
}

export const hasSeenPopup = (): boolean => {
  try {
    return sessionStorage.getItem(POPUP_SEEN_KEY) === '1'
  } catch {
    return false
  }
}

export const clearPopupSeen = (): void => {
  try {
    sessionStorage.removeItem(POPUP_SEEN_KEY)
  } catch {
    // ignore
  }
}
