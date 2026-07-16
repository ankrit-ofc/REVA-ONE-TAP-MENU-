/**
 * Thin promise wrapper around the browser Geolocation API.
 *
 * Used by both the customer geofence-scan flow and the admin "Use my current
 * location" button. Rejects with a typed reason so callers can show the right
 * message (permission denied vs. unavailable vs. insecure context, etc.).
 *
 * Note: geolocation only works on secure origins (HTTPS or localhost). On an
 * insecure origin `navigator.geolocation` exists but every call fails — we detect
 * that up front and report `insecure`.
 */

export interface DevicePosition {
  latitude: number
  longitude: number
  accuracy: number
}

export type GeolocationFailureKind =
  | 'unsupported' // browser has no Geolocation API
  | 'insecure' // page is not a secure context (no HTTPS)
  | 'denied' // user blocked the permission
  | 'unavailable' // position could not be determined
  | 'timeout' // took too long to get a fix

export class GeolocationError extends Error {
  kind: GeolocationFailureKind
  constructor(kind: GeolocationFailureKind, message?: string) {
    super(message ?? kind)
    this.name = 'GeolocationError'
    this.kind = kind
  }
}

export function getDevicePosition(): Promise<DevicePosition> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      reject(new GeolocationError('unsupported'))
      return
    }
    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      reject(new GeolocationError('insecure'))
      return
    }

    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      (err) => {
        if (err.code === err.PERMISSION_DENIED) reject(new GeolocationError('denied'))
        else if (err.code === err.TIMEOUT) reject(new GeolocationError('timeout'))
        else reject(new GeolocationError('unavailable'))
      },
      // High accuracy for a real GPS fix; allow a recent cached fix so page
      // reloads don't re-prompt or re-acquire from scratch.
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    )
  })
}
