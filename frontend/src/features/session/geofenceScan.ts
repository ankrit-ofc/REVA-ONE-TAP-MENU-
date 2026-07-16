/**
 * Shared scan flow with the geofence "428 handshake".
 *
 * Both the initial scan (Scan.tsx) and the silent session restore on reload
 * (RequireSession.tsx) go through here so the handshake lives in one place:
 *
 *   1. POST /scan with no coordinates.
 *   2. If the restaurant doesn't require location → success (no prompt ever).
 *   3. If it does → backend replies 428; we request the device location and
 *      retry /scan with coordinates. The backend then accepts (within radius)
 *      or rejects with 403 (too far).
 *
 * getDevicePosition() may throw a GeolocationError (denied/insecure/…); callers
 * translate that into the right "enable location" UI.
 */
import { getDevicePosition } from '@/lib/geolocation'
import type { ScanRequest, SessionResponse } from '@/lib/schemas/session'

type ScanTrigger = (arg: ScanRequest) => { unwrap: () => Promise<SessionResponse> }

function statusOf(e: unknown): number | undefined {
  return typeof e === 'object' && e !== null && 'status' in e
    ? (e as { status?: number }).status
    : undefined
}

export async function scanWithGeofence(
  scan: ScanTrigger,
  qrToken: string,
): Promise<SessionResponse> {
  try {
    return await scan({ qr_token: qrToken }).unwrap()
  } catch (e) {
    if (statusOf(e) !== 428) throw e
    // Restaurant requires location — get a fix and retry.
    const pos = await getDevicePosition()
    return await scan({
      qr_token: qrToken,
      latitude: pos.latitude,
      longitude: pos.longitude,
      accuracy: pos.accuracy,
    }).unwrap()
  }
}
