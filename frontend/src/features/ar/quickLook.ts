/**
 * iOS AR Quick Look launcher.
 *
 * We launch Quick Look ourselves instead of using <model-viewer>'s own
 * ios-src handoff (removed — see TableArView.tsx's own history/comments):
 * Quick Look is a native view that can't render model-viewer's DOM hotspot
 * overlays, so nutrition tags never showed for iOS users. This launches
 * Quick Look with Apple's custom-banner fragment
 * (#custom=<https-url>&customHeight=…) instead, so nutrition data still
 * shows — as a compact bottom sheet (GET /ar-banner/{productId}) rather than
 * 3D-anchored cards.
 *
 * Mechanism: a `rel="ar"` anchor with an <img> child, clicked synchronously
 * inside the caller's event handler — the same trick <model-viewer> used
 * internally when ios-src was wired. The click must stay in the same tick as
 * the user gesture, or Safari won't treat the AR launch as user-activated.
 */

// 1x1 transparent GIF — Quick Look requires the rel="ar" anchor to have an
// <img> child (used as its loading poster); this guarantees one exists even
// for a product with no photo.
const TRANSPARENT_PIXEL =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7'

/**
 * True only where `<a rel="ar">` Quick Look actually works. Every iOS
 * browser (Safari, Chrome-for-iOS, Firefox-for-iOS, …) is WebKit under the
 * hood, so this is a direct capability query rather than iOS/UA sniffing —
 * and it naturally reports false on Android, desktop, older iOS, and most
 * in-app browser web views, which is exactly the fallback behaviour we want
 * (see TableArView.tsx: those all fall through to the existing WebXR/orbit
 * popup path, unchanged).
 */
export const supportsQuickLookAR: boolean = (() => {
  try {
    return document.createElement('a').relList.supports('ar')
  } catch {
    return false
  }
})()

const CUSTOM_HEIGHT = 'medium'

/**
 * Launch AR Quick Look for `usdzUrl` with a custom nutrition banner backed by
 * GET /ar-banner/{productId}. Must be called synchronously from within a
 * user-gesture event handler (a click — not a promise/timeout callback), or
 * iOS Safari won't honour the launch.
 */
export function launchQuickLook(usdzUrl: string, productId: string, posterUrl?: string | null): void {
  // Absolute on purpose: this is text Quick Look parses on its own side from
  // the fragment, not something the browser resolves for us the way it does
  // for the anchor's own href below.
  const bannerUrl = `${window.location.origin}/ar-banner/${productId}`
  const href = `${usdzUrl}#custom=${encodeURIComponent(bannerUrl)}&customHeight=${CUSTOM_HEIGHT}`

  const anchor = document.createElement('a')
  anchor.setAttribute('rel', 'ar')
  anchor.setAttribute('href', href)
  anchor.style.display = 'none'

  const img = document.createElement('img')
  img.src = posterUrl || TRANSPARENT_PIXEL
  anchor.appendChild(img)

  document.body.appendChild(anchor)
  anchor.click()
  // Quick Look has already taken the handoff by the time this fires; the
  // anchor only needs to outlive the synchronous click dispatch.
  setTimeout(() => anchor.remove(), 2000)
}
