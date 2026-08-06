import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { AnnotationPublic } from '@/lib/schemas/menu'
import { useHotspotFanOffsets } from '@/hooks/useHotspotFanOffsets'
import styles from './TableArView.module.css'

interface Props {
  /** URL to the .glb model (Android WebXR / desktop WebGL). */
  src: string
  /** URL to the .usdz model for iOS AR Quick Look. */
  iosSrc?: string
  /** Accessible description of the dish (model alt text). */
  alt: string
  /** className applied to the action button so the page controls its look. */
  className?: string
  /**
   * Admin-verified nutrition hotspots (already filtered server-side to
   * admin_verified + published — see menu_service._product_public). Absent/empty
   * for a product with no tags: renders nothing extra, no layout shift.
   */
  annotations?: AnnotationPublic[] | null
}

/** The subset of the <model-viewer> element API we touch. */
type ModelViewerElement = HTMLElement & {
  loaded?: boolean
  canActivateAR?: boolean
  activateAR?: () => Promise<void>
}

function formatMacro(value: number | null): string | null {
  if (value == null) return null
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

// A tag still at its DB default position — the admin never placed it (see the same
// check in Model3DEditor.tsx). Customer annotations are already filtered server-side
// to admin_verified, but a tag can in principle be verified before ever being placed,
// so this guard is still needed: render nothing rather than a card at the mesh origin.
function isUnplaced(a: Pick<AnnotationPublic, 'position_x' | 'position_y' | 'position_z'>): boolean {
  return a.position_x === 0 && a.position_y === 0 && a.position_z === 0
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
 *
 * Nutrition hotspots: each admin-verified, placed annotation renders as a floating
 * card outside the dish — a small anchor dot exactly at the placed 3D point, a thin
 * leader line, and a card with the component name + macros + allergens pushed radially
 * outward from the viewer's center toward wherever the dot currently projects on
 * screen (see useHotspotFanOffsets) so it clears the dish at any camera angle,
 * including through auto-rotate. This is a `slot="hotspot-{id}"` child of
 * `<model-viewer>`, which positions the anchor in screen space every frame — the card
 * stays upright and readable at any orbit angle "for free" (it's normal DOM layout
 * pinned to a projected 2D point, never 3D-rotated), both in the orbit preview and, per
 * model-viewer's own AR DOM-overlay support, during a live WebXR session — untested
 * here, no AR-capable device in this environment.
 */
export default function TableArView({ src, iosSrc, alt, className, annotations }: Props) {
  const [libReady, setLibReady] = useState(false)
  const [modelReady, setModelReady] = useState(false)
  const [, setCanAR] = useState(false)
  const [show3D, setShow3D] = useState(false)
  const ref = useRef<HTMLElement | null>(null)
  const dotRefs = useRef<Map<string, HTMLElement>>(new Map())

  const placed = (annotations ?? []).filter((a) => !isUnplaced(a))
  const hasAnnotations = placed.length > 0
  const placedIds = placed.map((a) => a.id)
  // Only run the per-frame layout loop while the popup orbit preview is actually
  // visible — the model-viewer stays mounted (eager-loading) even when hidden, and
  // its 1px hidden box has no meaningful screen space to fan cards around.
  const fanOffsets = useHotspotFanOffsets(ref, dotRefs, placedIds, {
    radiusFactor: 0.42,
    minRadius: 55,
    maxRadius: 140,
    active: show3D,
  })

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

  const closePopup = () => setShow3D(false)

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
              onClick={closePopup}
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
          >
            {hasAnnotations &&
              placed.map((a, i) => {
                // The card is pushed OUTWARD from the viewer's center toward wherever
                // the dot actually projects on screen right now — see
                // useHotspotFanOffsets — so it clears the dish at any camera angle,
                // including through auto-rotate. Fall back to the old top-start
                // clockwise sweep until the hook's first frame lands, so there's no
                // flash of the card sitting on top of the dish.
                const fallbackAng = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, placed.length)
                const fallbackR = 95 // px — shorter than the admin editor's default: mobile viewport
                const fo = fanOffsets[a.id]
                const cardVars: CSSProperties = {
                  ['--lx' as string]: `${fo?.lx ?? Math.cos(fallbackAng) * fallbackR}px`,
                  ['--ly' as string]: `${fo?.ly ?? Math.sin(fallbackAng) * fallbackR}px`,
                  ['--len' as string]: `${fo?.len ?? fallbackR}px`,
                  ['--ang' as string]: `${fo?.ang ?? (fallbackAng * 180) / Math.PI}deg`,
                }
                const kcal = formatMacro(a.calories)
                const protein = formatMacro(a.protein_g)
                const carbs = formatMacro(a.carbs_g)
                const fat = formatMacro(a.fat_g)
                return (
                  <div
                    key={a.id}
                    slot={`hotspot-${a.id}`}
                    data-position={`${a.position_x} ${a.position_y} ${a.position_z}`}
                    data-normal={`${a.normal_x} ${a.normal_y} ${a.normal_z}`}
                    className={styles.callout}
                    style={cardVars}
                  >
                    <span
                      className={styles.dot}
                      ref={(el) => {
                        if (el) dotRefs.current.set(a.id, el)
                        else dotRefs.current.delete(a.id)
                      }}
                    />
                    <span className={styles.leader} />
                    <div className={styles.card}>
                      <p className={styles.cardLabel}>{a.label}</p>
                      {(kcal || protein || carbs || fat) && (
                        <div className={styles.cardMacros}>
                          {kcal && <span>{kcal} kcal</span>}
                          {protein && <span>P {protein}g</span>}
                          {carbs && <span>C {carbs}g</span>}
                          {fat && <span>F {fat}g</span>}
                        </div>
                      )}
                      {a.allergens.length > 0 && (
                        <p className={styles.cardAllergens}>Contains: {a.allergens.join(', ')}</p>
                      )}
                    </div>
                  </div>
                )
              })}
          </model-viewer>
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
