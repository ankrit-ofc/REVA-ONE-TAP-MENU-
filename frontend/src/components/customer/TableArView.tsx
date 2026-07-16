import { useEffect, useRef, useState, type CSSProperties } from 'react'

interface Props {
  /** URL to the .glb model (Android WebXR / desktop WebGL). */
  src: string
  /** URL to the .usdz model for iOS AR Quick Look. */
  iosSrc?: string
  /** Accessible description of the dish (model alt text). */
  alt: string
  /** className applied to the action button so the page controls its look. */
  className?: string
}

/** The subset of the <model-viewer> element API we touch. */
type ModelViewerElement = HTMLElement & {
  loaded?: boolean
  canActivateAR?: boolean
  activateAR?: () => Promise<void>
}

/**
 * "View on my table" AR launcher for the product detail page.
 *
 * The trick that makes AR reliable: the `<model-viewer>` is mounted **hidden** and
 * `loading="eager"`, so the model downloads + parses silently while the customer reads
 * the page. By the time they tap the button the model is already loaded, so
 * `activateAR()` runs **synchronously inside the click handler** — a real user gesture
 * with transient activation — and the camera opens on the first try. (Auto-launching
 * from the async `load` callback fails because that has no user activation.)
 *
 * AR engine: Android in-page WebXR (no Scene Viewer), iOS AR Quick Look via `ios-src`.
 * Desktop / no-AR devices can't open the camera, so the button reveals an inline 3D
 * orbit preview instead.
 */
export default function TableArView({ src, iosSrc, alt, className }: Props) {
  const [libReady, setLibReady] = useState(false)
  const [modelReady, setModelReady] = useState(false)
  const [canAR, setCanAR] = useState(false)
  const [show3D, setShow3D] = useState(false)
  const ref = useRef<HTMLElement | null>(null)

  // Lazy-load the model-viewer library (bundles three.js).
  useEffect(() => {
    let active = true
    import('@google/model-viewer')
      .then(() => {
        if (active) setLibReady(true)
      })
      .catch(() => {
        /* offline / unsupported — button stays in "Preparing…" */
      })
    return () => {
      active = false
    }
  }, [])

  // Track when the model has finished loading, and whether AR is available.
  useEffect(() => {
    if (!libReady) return
    const el = ref.current as ModelViewerElement | null
    if (!el) return
    const onLoad = () => {
      setModelReady(true)
      setCanAR(Boolean(el.canActivateAR))
    }
    if (el.loaded) onLoad()
    el.addEventListener('load', onLoad)
    return () => el.removeEventListener('load', onLoad)
  }, [libReady])

  const handleClick = () => {
    const el = ref.current as ModelViewerElement | null
    if (!el) return
    if (el.canActivateAR && el.activateAR) {
      // Reliable: model already loaded, this call is inside the tap's gesture.
      // If AR still can't start (permission/engine), fall back to the popup viewer.
      el.activateAR().catch(() => setShow3D(true))
    } else {
      // No camera AR (desktop) — open the popup 3D orbit viewer.
      setShow3D(true)
    }
  }

  const busy = !libReady || !modelReady
  const label = busy ? 'Preparing 3D…' : 'View on my table'

  return (
    <>
      <button type="button" className={className} onClick={handleClick} disabled={busy} aria-busy={busy}>
        {label}
      </button>

      {/* The model-viewer stays mounted continuously so it eager-loads once and stays
          AR-ready. When show3D is false it's a 1px hidden loader; when true its wrapper
          becomes a full-screen popup with an orbit preview. */}
      {libReady && (
        <div style={show3D ? overlayStyle : hiddenWrap} aria-hidden={!show3D}>
          {show3D && (
            <button
              type="button"
              onClick={() => setShow3D(false)}
              aria-label="Close 3D viewer"
              style={closeBtnStyle}
            >
              ✕
            </button>
          )}
          <model-viewer
            ref={ref}
            src={src}
            ios-src={iosSrc}
            alt={alt}
            loading="eager"
            camera-controls
            auto-rotate
            ar
            ar-modes="webxr quick-look"
            ar-scale="auto"
            ar-placement="floor"
            shadow-intensity="1"
            touch-action="pan-y"
            style={{
              width: show3D ? 'min(92vw, 480px)' : '100%',
              height: show3D ? 'min(70vh, 480px)' : '1px',
              background: '#f1f5f9',
              borderRadius: '0.75rem',
            }}
          />
        </div>
      )}
    </>
  )
}

// Rendered but invisible so the model still eager-loads (display:none would stop it).
const hiddenWrap: CSSProperties = {
  height: '1px',
  overflow: 'hidden',
  opacity: 0,
  pointerEvents: 'none',
}

// Full-screen dim popup that hosts the orbit preview when AR isn't available.
const overlayStyle: CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 1000,
  background: 'rgba(0, 0, 0, 0.72)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '1rem',
}

const closeBtnStyle: CSSProperties = {
  position: 'absolute',
  top: '1rem',
  right: '1rem',
  width: '2.5rem',
  height: '2.5rem',
  borderRadius: '9999px',
  border: 'none',
  background: 'rgba(255, 255, 255, 0.9)',
  color: '#111',
  fontSize: '1.1rem',
  fontWeight: 700,
  cursor: 'pointer',
}
