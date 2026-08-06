import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  useUpdateAnnotationMutation,
  useDeleteAnnotationMutation,
  useCreateAnnotationMutation,
  usePublishModelMutation,
  type AnnotationInput,
} from '@/features/admin/adminApi'
import type { AnnotationResponse, ModelStatusResponse } from '@/lib/schemas/admin'
import { useHotspotFanOffsets } from '@/hooks/useHotspotFanOffsets'
import styles from './Model3DEditor.module.css'

/** The bits of the <model-viewer> element we call for click-to-reposition. */
type ModelViewerEl = HTMLElement & {
  positionAndNormalFromPoint?: (
    x: number,
    y: number,
  ) => { position: { toString(): string }; normal: { toString(): string } } | null
}

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

function numOrNull(s: string): number | null {
  const t = s.trim()
  if (t === '') return null
  const n = Number(t)
  return isNaN(n) ? null : n
}

function formatMacro(value: number | null): string | null {
  if (value == null) return null
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

// A tag still at its DB default position — never deliberately placed. Real placement
// (a click on the model, or a legacy hand-set position) practically never lands on
// exactly (0,0,0), so this sentinel-equality check is safe.
function isUnplaced(a: Pick<AnnotationResponse, 'position_x' | 'position_y' | 'position_z'>): boolean {
  return a.position_x === 0 && a.position_y === 0 && a.position_z === 0
}

// <model-viewer> is a custom element (hyphenated tag name). React 18 does not map the
// `className` prop to the `class` attribute for custom elements the way it does for
// built-in HTML tags, so a CSS-module className here is silently a no-op: the intended
// size never applies, the element collapses to a small default box, and
// positionAndNormalFromPoint()'s ray has nothing correctly framed to hit — this is
// exactly what broke click-to-reposition. Set size via the `style` prop instead (as
// TableArView.tsx already does correctly). Do not "clean this up" back to className.
const viewerStyle: CSSProperties = {
  width: '100%',
  height: '360px',
  background: '#f1f5f9',
  borderRadius: '0.6rem',
}

// A pointer release counts as a placement tap (not a camera drag) only inside these
// bounds — mirrors the TAP_DISTANCE/TAP_MS heuristic camera-controls itself uses for
// its own tap-to-recenter (see SmoothControls.js in @google/model-viewer).
const TAP_MAX_DISTANCE_PX = 5
const TAP_MAX_DURATION_MS = 300

// Why a correctly-placed tag still visibly "moves": two SEPARATE built-in
// model-viewer behaviors silently shift the camera after our own placement logic
// has already run and saved the right 3D point.
//   1. SmoothControls.onPointerUp calls recenter() on every tap release (same
//      TAP_DISTANCE/TAP_MS window we mirror above for our own tap detection — see
//      `enablePan && enableTap` in SmoothControls.js) — it RE-TARGETS THE CAMERA
//      at whatever point was tapped. This fires on every one of our placement taps,
//      confirmed live: getCameraTarget() moves off (0,0,0) after a tap even though
//      getCameraOrbit() (theta/phi/radius) is unchanged. Since a hotspot's screen
//      position depends on the target, not just the orbit angles, every OTHER
//      already-placed marker appears to jump too. `disable-tap` turns this off
//      without touching drag-to-orbit or drag-to-pan.
//   2. The idle "drag hint" (interaction-prompt, default threshold 3000ms — see
//      DEFAULT_INTERACTION_PROMPT_THRESHOLD in features/controls.js) nudges the
//      camera after a few seconds of inactivity, which reads the same way if the
//      admin doesn't look immediately. `interaction-prompt="none"` turns this off;
//      the editor already has its own explicit placement affordance (hint text +
//      Cancel button), so the built-in nudge is redundant here regardless.
// Do not re-enable either without re-verifying markers stay put after a tap.

// ── One editable nutrition tag ──────────────────────────────────────────────────

function AnnotationRow({
  productId,
  ann,
  selected,
  onSelect,
}: {
  productId: string
  ann: AnnotationResponse
  selected: boolean
  onSelect: () => void
}) {
  const [label, setLabel] = useState(ann.label)
  const [calories, setCalories] = useState(ann.calories?.toString() ?? '')
  const [protein, setProtein] = useState(ann.protein_g?.toString() ?? '')
  const [carbs, setCarbs] = useState(ann.carbs_g?.toString() ?? '')
  const [fat, setFat] = useState(ann.fat_g?.toString() ?? '')
  const [allergens, setAllergens] = useState((ann.allergens ?? []).join(', '))
  const [err, setErr] = useState<string | null>(null)

  const [updateAnn, { isLoading: saving }] = useUpdateAnnotationMutation()
  const [deleteAnn, { isLoading: deleting }] = useDeleteAnnotationMutation()

  const verified = ann.status === 'ADMIN_VERIFIED'
  const unplaced = isUnplaced(ann)

  const save = async () => {
    setErr(null)
    if (!label.trim()) { setErr('Label required.'); return }
    const body: AnnotationInput = {
      label: label.trim(),
      calories: numOrNull(calories),
      protein_g: numOrNull(protein),
      carbs_g: numOrNull(carbs),
      fat_g: numOrNull(fat),
      allergens: allergens.split(',').map((a) => a.trim()).filter(Boolean),
    }
    try {
      await updateAnn({ productId, annotationId: ann.id, body }).unwrap()
    } catch (e) { setErr(errDetail(e)) }
  }

  return (
    <div
      className={`${styles.row} ${selected ? styles.rowSelected : ''}`}
      onClick={onSelect}
    >
      <div className={styles.rowHead}>
        <span
          className={`${styles.trustDot} ${verified ? styles.trustGreen : styles.trustAi}`}
          title={verified ? 'Human-verified' : 'AI estimate'}
        />
        <input
          className={styles.labelInput}
          value={label}
          onChange={(e) => setLabel(e.target.value.slice(0, 120))}
          placeholder="Component"
        />
        {unplaced && <span className={styles.unplacedBadge}>Not placed</span>}
      </div>
      <div className={styles.nutrients}>
        <label>kcal<input value={calories} onChange={(e) => setCalories(e.target.value)} inputMode="decimal" /></label>
        <label>P (g)<input value={protein} onChange={(e) => setProtein(e.target.value)} inputMode="decimal" /></label>
        <label>C (g)<input value={carbs} onChange={(e) => setCarbs(e.target.value)} inputMode="decimal" /></label>
        <label>F (g)<input value={fat} onChange={(e) => setFat(e.target.value)} inputMode="decimal" /></label>
      </div>
      <input
        className={styles.allergens}
        value={allergens}
        onChange={(e) => setAllergens(e.target.value)}
        placeholder="Allergens (comma-separated)"
      />
      {err && <span className={styles.err}>{err}</span>}
      <div className={styles.rowActions}>
        <button type="button" className={styles.saveBtn} disabled={saving} onClick={save}>
          {saving ? 'Saving…' : 'Save (verify)'}
        </button>
        <button
          type="button"
          className={styles.delBtn}
          disabled={deleting}
          onClick={(e) => { e.stopPropagation(); void deleteAnn({ productId, annotationId: ann.id }) }}
        >
          Delete
        </button>
      </div>
    </div>
  )
}

// ── Editor modal ────────────────────────────────────────────────────────────────

export default function Model3DEditor({
  productId,
  status,
  onClose,
}: {
  productId: string
  status: ModelStatusResponse
  onClose: () => void
}) {
  const [libReady, setLibReady] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [banner, setBanner] = useState<string | null>(null)
  const viewerRef = useRef<HTMLElement | null>(null)
  const pointerDownRef = useRef<{ x: number; y: number; time: number; pointerId: number } | null>(null)
  const dotRefs = useRef<Map<string, HTMLElement>>(new Map())

  const [createAnn] = useCreateAnnotationMutation()
  const [updateAnn] = useUpdateAnnotationMutation()
  const [publish, { isLoading: publishing }] = usePublishModelMutation()

  useEffect(() => {
    let active = true
    import('@google/model-viewer')
      .then(() => { if (active) setLibReady(true) })
      .catch(() => setBanner('3D viewer failed to load.'))
    return () => { active = false }
  }, [])

  const annotations = status.annotations
  const published = status.model_published
  const selectedTag = annotations.find((a) => a.id === selectedId) ?? null
  const placedIds = annotations.filter((a) => !isUnplaced(a)).map((a) => a.id)
  // Card leader length is a fraction of the viewer's own box, not a fixed pixel
  // value, so it clears the dish regardless of how large the modal renders it.
  const fanOffsets = useHotspotFanOffsets(viewerRef, dotRefs, placedIds, {
    radiusFactor: 0.42,
    minRadius: 90,
    maxRadius: 190,
    active: libReady && Boolean(status.model_glb_url),
  })

  // <model-viewer> with camera-controls rotates the camera on ANY nonzero pointer
  // movement between press and release (SmoothControls.onPointerMove — see
  // node_modules/@google/model-viewer/lib/three-components/SmoothControls.js — treats
  // even a 1px delta as an orbit drag). A plain onClick still fires after that, but by
  // then the camera has already moved, so positionAndNormalFromPoint no longer targets
  // what the user actually saw under their cursor/finger. Scripted, pixel-perfect
  // clicks never trigger that drift, which is why this looked fixed under automation
  // but not to a real mouse, trackpad, or touch user. Fix: track the press ourselves
  // and only treat release as a placement tap when it moved under TAP_MAX_DISTANCE_PX
  // in under TAP_MAX_DURATION_MS — anything past that is a drag, and we do nothing so
  // camera-controls' own orbit handling is untouched. Pointer events (not click) so
  // mouse, trackpad, and touch share one code path. Do not swap this back to onClick.
  const onModelPointerDown = (e: React.PointerEvent) => {
    if (e.altKey) return // model-viewer's own idle "drag hint" animation dispatches synthetic PointerEvents with altKey:true — not a real user gesture.
    pointerDownRef.current = { x: e.clientX, y: e.clientY, time: performance.now(), pointerId: e.pointerId }
  }

  const onModelPointerUp = async (e: React.PointerEvent) => {
    const start = pointerDownRef.current
    if (e.altKey) return
    if (!start) return
    // Only consume the press we actually recorded — a stray/duplicate pointerup for a
    // different pointerId (or one that arrives after we've already consumed this
    // press) must not silently reuse stale start coordinates.
    if (e.pointerId !== start.pointerId) return
    pointerDownRef.current = null
    const movedPx = Math.hypot(e.clientX - start.x, e.clientY - start.y)
    const elapsedMs = performance.now() - start.time
    if (movedPx > TAP_MAX_DISTANCE_PX || elapsedMs > TAP_MAX_DURATION_MS) return
    if (!selectedId) return
    const el = viewerRef.current as ModelViewerEl | null
    if (!el?.positionAndNormalFromPoint) return
    // positionAndNormalFromPoint expects RAW CLIENT (viewport) coordinates, not
    // element-relative ones — confirmed by reading the source, not assumed: its
    // internal getNDC(clientX, clientY) (three-components/ModelScene.js) does its own
    // `(clientX - rect.x) / this.width` conversion using the element's CURRENT
    // getBoundingClientRect(). Subtracting rect.left/top here ourselves before calling
    // it double-subtracts the element's offset, shifting the effective ray by roughly
    // rect.left/rect.top pixels — confirmed live: for one physical click point,
    // pre-subtracting produced a miss while passing e.clientX/e.clientY raw hit
    // correctly, at the exact same screen position. Do not reintroduce rect.left/top
    // here — pass e.clientX/e.clientY straight through.
    const hit = el.positionAndNormalFromPoint(e.clientX, e.clientY)
    if (!hit) {
      setBanner('No surface there — click directly on the dish.')
      return
    }
    // model-viewer stringifies coords with a unit suffix ("0.12m 0.34m 0.56m"), so
    // parseFloat (not Number, which would yield NaN → null → a NOT NULL 500) is required.
    const nums = (s: string) => s.trim().split(/\s+/).map((t) => parseFloat(t))
    const [px, py, pz] = nums(hit.position.toString())
    const [nx, ny, nz] = nums(hit.normal.toString())
    if ([px, py, pz, nx, ny, nz].some((v) => !Number.isFinite(v))) {
      setBanner('Could not read that point — try again.')
      return
    }
    setBanner(null)
    try {
      await updateAnn({
        productId,
        annotationId: selectedId,
        body: { position_x: px, position_y: py, position_z: pz, normal_x: nx, normal_y: ny, normal_z: nz },
      }).unwrap()
    } catch { setBanner('Could not reposition tag.') }
  }

  const addTag = async () => {
    try {
      // No position override: a manually added tag starts at the same (0,0,0) "not
      // placed" sentinel as a fresh AI draft, so it reads as unplaced until the admin
      // clicks the model — same rule for both creation paths.
      const created = await createAnn({ productId, body: { label: 'New tag' } }).unwrap()
      setSelectedId(created.id)
    } catch (e) { setBanner(errDetail(e)) }
  }

  const togglePublish = async () => {
    setBanner(null)
    try {
      await publish({ productId, published: !published }).unwrap()
    } catch (e) { setBanner(errDetail(e)) }
  }

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h3 className={styles.title}>3D Model Editor</h3>
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close">×</button>
        </div>

        {banner && <p className={styles.banner}>{banner}</p>}

        <div className={styles.grid}>
          <div className={styles.viewerCol}>
            {libReady && status.model_glb_url ? (
              <model-viewer
                ref={viewerRef}
                src={status.model_glb_url}
                alt="Product 3D model"
                camera-controls
                interaction-prompt="none"
                disable-tap
                shadow-intensity="1"
                style={viewerStyle}
                onPointerDown={onModelPointerDown}
                onPointerUp={onModelPointerUp}
              >
                {annotations.filter((a) => !isUnplaced(a)).map((a, i, placed) => {
                  // The card is pushed OUTWARD from the viewer's center (toward wherever
                  // the dot actually projects on screen right now), not toward a fixed
                  // per-tag angle — see useHotspotFanOffsets. That's what keeps it clear
                  // of the dish as the camera orbits, not just at the initial angle. Until
                  // the hook's first frame lands, fall back to the old top-start clockwise
                  // sweep so there's no flash of the card sitting on top of the dish.
                  const fallbackAng = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, placed.length)
                  const fallbackR = 130
                  const fo = fanOffsets[a.id]
                  const calloutVars: CSSProperties = {
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
                    <button
                      key={a.id}
                      type="button"
                      slot={`hotspot-${a.id}`}
                      data-position={`${a.position_x} ${a.position_y} ${a.position_z}`}
                      data-normal={`${a.normal_x} ${a.normal_y} ${a.normal_z}`}
                      className={`${styles.callout} ${a.id === selectedId ? styles.calloutSel : ''} ${a.status === 'ADMIN_VERIFIED' ? styles.calloutVerified : styles.calloutAi}`}
                      style={calloutVars}
                      // Stop the pointerdown here too (not just click) — otherwise a tap
                      // on an existing marker would both select it AND register as a
                      // placement tap for whatever tag was already selected.
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => { e.stopPropagation(); setSelectedId(a.id) }}
                    >
                      {/* Dot on the component point → straight leader → upright card, so
                          placement previews exactly what the customer's floating card
                          (TableArView.tsx) will show. */}
                      <span
                        className={styles.dot}
                        ref={(el) => {
                          if (el) dotRefs.current.set(a.id, el)
                          else dotRefs.current.delete(a.id)
                        }}
                      />
                      <span className={styles.leader} />
                      <span className={styles.labelChip}>
                        <span className={styles.labelChipName}>{a.label}</span>
                        {(kcal || protein || carbs || fat) && (
                          <span className={styles.labelChipMacros}>
                            {kcal && <span>{kcal} kcal</span>}
                            {protein && <span>P {protein}g</span>}
                            {carbs && <span>C {carbs}g</span>}
                            {fat && <span>F {fat}g</span>}
                          </span>
                        )}
                        {a.allergens.length > 0 && (
                          <span className={styles.labelChipAllergens}>Contains: {a.allergens.join(', ')}</span>
                        )}
                      </span>
                    </button>
                  )
                })}
              </model-viewer>
            ) : (
              <div className={styles.viewerLoading}>Loading 3D model…</div>
            )}
            {selectedId ? (
              <div className={styles.placeHint}>
                <p className={styles.hint}>
                  Click on the model to place <strong>{selectedTag?.label ?? 'this tag'}</strong>.
                </p>
                <button type="button" className={styles.cancelBtn} onClick={() => setSelectedId(null)}>
                  Cancel
                </button>
              </div>
            ) : (
              <p className={styles.hint}>Select a tag to place it on the model.</p>
            )}
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <span className={styles.panelTitle}>Nutrition tags</span>
              <button type="button" className={styles.addBtn} onClick={() => void addTag()}>+ Add tag</button>
            </div>
            <p className={styles.legend}>
              <span className={`${styles.trustDot} ${styles.trustGreen}`} /> verified&nbsp;&nbsp;
              <span className={`${styles.trustDot} ${styles.trustAi}`} /> AI estimate
            </p>
            <div className={styles.rows}>
              {annotations.length === 0 && <p className={styles.empty}>No tags yet. Add one.</p>}
              {annotations.map((a) => (
                <AnnotationRow
                  key={a.id}
                  productId={productId}
                  ann={a}
                  selected={a.id === selectedId}
                  onSelect={() => setSelectedId(a.id)}
                />
              ))}
            </div>

            <div className={styles.publishBar}>
              <span className={published ? styles.pubOn : styles.pubOff}>
                {published ? '● Published to customers' : '○ Not published'}
              </span>
              <button
                type="button"
                className={published ? styles.unpublishBtn : styles.publishBtn}
                disabled={publishing}
                onClick={() => void togglePublish()}
              >
                {publishing ? '…' : published ? 'Unpublish' : 'Publish'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
