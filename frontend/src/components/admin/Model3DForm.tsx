import { useEffect, useRef, useState } from 'react'
import {
  useGetModelStatusQuery,
  useUploadModelViewMutation,
  useGenerateModelMutation,
} from '@/features/admin/adminApi'
import type { ArModelStatus, ProductView } from '@/lib/schemas/admin'
import Model3DEditor from './Model3DEditor'
import styles from './Model3DForm.module.css'

const MAX_FILE_MB = 25
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

// Front/back/left/right feed 3D generation; top feeds nutrition marking.
const VIEWS: { key: ProductView; label: string; hint: string }[] = [
  { key: 'FRONT', label: 'Front', hint: 'Straight-on' },
  { key: 'BACK', label: 'Back', hint: 'Rear' },
  { key: 'LEFT', label: 'Left', hint: 'Left side' },
  { key: 'RIGHT', label: 'Right', hint: 'Right side' },
  { key: 'TOP', label: 'Top', hint: 'Top-down (for nutrition)' },
]

function validateImage(file: File): string | null {
  if (!ALLOWED_TYPES.includes(file.type)) return 'Only JPEG, PNG, or WebP images allowed.'
  if (file.size > MAX_FILE_MB * 1024 * 1024) return `Image must be under ${MAX_FILE_MB} MB.`
  return null
}

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Upload failed'
}

/** One labeled view slot — thumbnail (if captured) + upload/replace button. */
function ViewSlot({
  productId,
  view,
  label,
  hint,
  imageUrl,
}: {
  productId: string
  view: ProductView
  label: string
  hint: string
  imageUrl?: string
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploadView, { isLoading }] = useUploadModelViewMutation()
  const [err, setErr] = useState<string | null>(null)

  const pick = async (file: File) => {
    setErr(null)
    const v = validateImage(file)
    if (v) { setErr(v); return }
    try {
      await uploadView({ productId, view, file }).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  return (
    <div className={styles.slot}>
      <div className={styles.thumbWrap}>
        {imageUrl
          ? <img src={imageUrl} alt={`${label} view`} className={styles.thumb} />
          : <div className={styles.thumbEmpty} aria-hidden>📷</div>}
      </div>
      <div className={styles.slotMeta}>
        <span className={styles.slotLabel}>{label}</span>
        <span className={styles.slotHint}>{hint}</span>
        {err && <span className={styles.slotErr}>{err}</span>}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) void pick(f) }}
      />
      <button
        type="button"
        className={styles.slotBtn}
        disabled={isLoading}
        onClick={() => fileRef.current?.click()}
      >
        {isLoading ? 'Uploading…' : imageUrl ? 'Replace' : 'Upload'}
      </button>
    </div>
  )
}

const STATUS_LABEL: Record<ArModelStatus, string> = {
  NONE: 'No model',
  PENDING: 'Views captured',
  GENERATING: 'Generating…',
  READY: 'Ready',
  FAILED: 'Failed',
}

// Admin-selectable fal 3D models (label carries the per-generation cost). The backend
// enum validates the key, so this list can't drift into an invalid request.
const THREED_MODELS: { key: string; label: string }[] = [
  { key: 'hunyuan3d-v2-multiview', label: 'Hunyuan3D v2 multi-view · ~$0.05' },
  { key: 'trellis-multi', label: 'Trellis · ~$0.02' },
  { key: 'hunyuan3d-v3', label: 'Hunyuan3D v3 · $0.375' },
]
const DEFAULT_MODEL = 'hunyuan3d-v2-multiview'
const MODEL_KEYS = THREED_MODELS.map((m) => m.key)

/**
 * "Add 3D model" sub-form (edit mode only — needs a saved product).
 * Captures the 5 labeled source photos, then queues generation + nutrition marking.
 * While GENERATING it polls the status endpoint until the product flips to READY.
 */
export default function Model3DForm({ productId }: { productId: string }) {
  // Poll while a run is in flight so the badge flips to READY without a manual refresh.
  const [polling, setPolling] = useState(false)
  const [editing, setEditing] = useState(false)
  const { data: status, isLoading } = useGetModelStatusQuery(productId, {
    pollingInterval: polling ? 1500 : 0,
  })
  const [generate, { isLoading: generating }] = useGenerateModelMutation()
  const [err, setErr] = useState<string | null>(null)
  const [model, setModel] = useState<string>(DEFAULT_MODEL)

  // Default the dropdown to this product's last-used model (once, when status loads).
  const modelInit = useRef(false)
  useEffect(() => {
    if (modelInit.current || !status) return
    modelInit.current = true
    const lastGen = (status.jobs ?? [])
      .filter((j) => j.kind === 'GENERATION')
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
    if (lastGen && MODEL_KEYS.includes(lastGen.provider)) setModel(lastGen.provider)
  }, [status])

  const byView = new Map((status?.views ?? []).map((v) => [v.view, v.image_url]))
  const captured = byView.size
  const modelStatus: ArModelStatus = status?.model_status ?? 'NONE'
  const allCaptured = captured >= VIEWS.length
  const inFlight = modelStatus === 'GENERATING'

  // Poll while generating; stop once the status settles (READY/FAILED/etc.).
  useEffect(() => {
    setPolling(inFlight)
  }, [inFlight])

  const runGenerate = async () => {
    setErr(null)
    try {
      await generate({ productId, model }).unwrap()
      setPolling(true)
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  const badgeClass =
    modelStatus === 'READY' ? styles.badgeReady
      : modelStatus === 'FAILED' ? styles.badgeFailed
      : modelStatus === 'GENERATING' ? styles.badgeBusy
      : styles.badge

  return (
    <div className={styles.section}>
      <div className={styles.head}>
        <span className={styles.title}>3D Model (AR)</span>
        <span className={badgeClass}>
          {isLoading ? 'Loading…' : `Views ${captured}/5 · ${STATUS_LABEL[modelStatus]}`}
        </span>
      </div>
      <p className={styles.blurb}>
        Optional. Upload five labeled photos so this dish can be viewed in AR on the
        customer's table. Front / back / left / right build the 3D model; the top-down
        photo is used for nutrition tags.
      </p>
      <div className={styles.grid}>
        {VIEWS.map((v) => (
          <ViewSlot
            key={v.key}
            productId={productId}
            view={v.key}
            label={v.label}
            hint={v.hint}
            imageUrl={byView.get(v.key)}
          />
        ))}
      </div>

      <div className={styles.actions}>
        <label className={styles.modelRow}>
          Model
          <select
            className={styles.modelSelect}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={generating || inFlight}
          >
            {THREED_MODELS.map((m) => (
              <option key={m.key} value={m.key}>{m.label}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={styles.generateBtn}
          disabled={!allCaptured || generating || inFlight}
          onClick={() => void runGenerate()}
        >
          {inFlight ? 'Generating…' : modelStatus === 'READY' ? 'Regenerate' : 'Generate 3D model'}
        </button>
        {!allCaptured && (
          <span className={styles.slotHint}>Upload all 5 views to enable generation.</span>
        )}
        {modelStatus === 'READY' && (
          <div className={styles.readyRow}>
            <span className={styles.okNote}>
              Model ready — {status?.annotations.length ?? 0} nutrition tag(s)
              {status?.model_published ? ' · published' : ' · not published'}.
            </span>
            <button type="button" className={styles.editorBtn} onClick={() => setEditing(true)}>
              Open editor
            </button>
          </div>
        )}
        {modelStatus === 'FAILED' && (
          <span className={styles.slotErr}>Generation failed. Check the views and try again.</span>
        )}
        {err && <span className={styles.slotErr}>{err}</span>}
      </div>

      {editing && status && (
        <Model3DEditor productId={productId} status={status} onClose={() => setEditing(false)} />
      )}
    </div>
  )
}
