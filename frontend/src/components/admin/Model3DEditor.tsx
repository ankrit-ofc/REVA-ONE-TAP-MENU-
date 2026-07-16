import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  useUpdateAnnotationMutation,
  useDeleteAnnotationMutation,
  useCreateAnnotationMutation,
  usePublishModelMutation,
  type AnnotationInput,
} from '@/features/admin/adminApi'
import type { AnnotationResponse, ModelStatusResponse } from '@/lib/schemas/admin'
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

  // Click the model surface to move the selected hotspot there.
  const onModelClick = async (e: React.MouseEvent) => {
    if (!selectedId) return
    const el = viewerRef.current as ModelViewerEl | null
    if (!el?.positionAndNormalFromPoint) return
    const rect = el.getBoundingClientRect()
    const hit = el.positionAndNormalFromPoint(e.clientX - rect.left, e.clientY - rect.top)
    if (!hit) return
    // model-viewer stringifies coords with a unit suffix ("0.12m 0.34m 0.56m"), so
    // parseFloat (not Number, which would yield NaN → null → a NOT NULL 500) is required.
    const nums = (s: string) => s.trim().split(/\s+/).map((t) => parseFloat(t))
    const [px, py, pz] = nums(hit.position.toString())
    const [nx, ny, nz] = nums(hit.normal.toString())
    if ([px, py, pz, nx, ny, nz].some((v) => !Number.isFinite(v))) {
      setBanner('Could not read that point — try again.')
      return
    }
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
      const created = await createAnn({ productId, body: { label: 'New tag', position_y: 0.03 } }).unwrap()
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
                shadow-intensity="1"
                className={styles.viewer}
                onClick={onModelClick}
              >
                {annotations.map((a, i) => {
                  // Fan each label out to its own angle around the dish so no two labels
                  // share a direction (start at the top, sweep clockwise). The dot stays on
                  // the component point; the leader line runs straight out to the label.
                  const ang = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, annotations.length)
                  const R = 112 // px — leader length / label distance from the dot
                  const calloutVars: CSSProperties = {
                    ['--lx' as string]: `${Math.cos(ang) * R}px`,
                    ['--ly' as string]: `${Math.sin(ang) * R}px`,
                    ['--len' as string]: `${R}px`,
                    ['--ang' as string]: `${(ang * 180) / Math.PI}deg`,
                  }
                  return (
                    <button
                      key={a.id}
                      type="button"
                      slot={`hotspot-${a.id}`}
                      data-position={`${a.position_x} ${a.position_y} ${a.position_z}`}
                      data-normal={`${a.normal_x} ${a.normal_y} ${a.normal_z}`}
                      className={`${styles.callout} ${a.id === selectedId ? styles.calloutSel : ''} ${a.status === 'ADMIN_VERIFIED' ? styles.calloutVerified : styles.calloutAi}`}
                      style={calloutVars}
                      onClick={(e) => { e.stopPropagation(); setSelectedId(a.id) }}
                    >
                      {/* Dot on the component point → straight leader → upright label chip. */}
                      <span className={styles.dot} />
                      <span className={styles.leader} />
                      <span className={styles.labelChip}>{a.label}</span>
                    </button>
                  )
                })}
              </model-viewer>
            ) : (
              <div className={styles.viewerLoading}>Loading 3D model…</div>
            )}
            <p className={styles.hint}>
              {selectedId
                ? 'Click on the model to move the selected tag.'
                : 'Select a tag to reposition it on the model.'}
            </p>
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
