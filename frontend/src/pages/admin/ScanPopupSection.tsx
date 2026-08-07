import { useRef, useState } from 'react'
import {
  useUploadPopupIllustrationMutation,
  useRemovePopupIllustrationMutation,
  useListProductsQuery,
} from '@/features/admin/adminApi'
import type { ProductResponse, SettingsResponse } from '@/lib/schemas/admin'
import type { ProductPublic } from '@/lib/schemas/menu'
import { deriveMenuTheme, type MenuThemeMode } from '@/lib/menuAccent'
import ScanPopupCard from '@/components/customer/ScanPopupCard'
import styles from './Settings.module.css'
import previewStyles from './ScanPopupSection.module.css'

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Save failed'
}

const ILLUSTRATION_MAX_MB = 25
const ILLUSTRATION_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Scan-popup illustration: upload with preview, replace, remove. Uploads
 *  apply immediately, mirroring the menu banner's own image upload. */
function PopupIllustrationSection({ illustrationUrl }: { illustrationUrl: string | null }) {
  const [upload, { isLoading: uploading }] = useUploadPopupIllustrationMutation()
  const [remove, { isLoading: removing }] = useRemovePopupIllustrationMutation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState<string | null>(null)

  const pick = async (file: File) => {
    setErr(null)
    if (!ILLUSTRATION_TYPES.includes(file.type)) { setErr('Only JPEG, PNG, or WebP images allowed.'); return }
    if (file.size > ILLUSTRATION_MAX_MB * 1024 * 1024) { setErr(`Image must be under ${ILLUSTRATION_MAX_MB} MB.`); return }
    try {
      await upload(file).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel}>Illustration</label>
      {illustrationUrl
        ? <img src={illustrationUrl} alt="Popup illustration" className={styles.illustrationPreview} />
        : <div className={styles.illustrationEmpty}>No illustration uploaded — that slot is hidden entirely.</div>}
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void pick(f)
          e.target.value = ''
        }}
      />
      <div className={styles.bannerActions}>
        <button
          type="button"
          className={styles.btnSecondary}
          disabled={uploading || removing}
          onClick={() => fileRef.current?.click()}
        >
          {uploading ? 'Uploading…' : illustrationUrl ? 'Replace illustration' : 'Upload illustration'}
        </button>
        {illustrationUrl && (
          <button
            type="button"
            className={styles.btnSecondary}
            disabled={uploading || removing}
            onClick={() => { setErr(null); void remove() }}
          >
            {removing ? 'Removing…' : 'Remove illustration'}
          </button>
        )}
      </div>
      {err && <p className={styles.geoErr}>{err}</p>}
      <p className={styles.hint}>
        Shown beside the speech-bubble quote. JPEG, PNG, or WebP up to {ILLUSTRATION_MAX_MB} MB
        and at most 1000×1000 px. Hidden entirely when not set.
      </p>
    </div>
  )
}

const MAX_POPUP_PRODUCTS = 5

/** Search-and-select picker for the popup's featured products (up to 5,
 *  orderable). Only active + available products are offered — anything else
 *  would never resolve on the customer menu anyway. */
function PopupProductPicker({
  productIds,
  onChange,
}: {
  productIds: string[]
  onChange: (ids: string[]) => void
}) {
  const { data: products } = useListProductsQuery()
  const [search, setSearch] = useState('')

  const available = (products ?? []).filter((p) => p.is_active && p.is_available)
  const byId = new Map(available.map((p) => [p.id, p]))
  const selected = productIds
    .map((id) => byId.get(id))
    .filter((p): p is ProductResponse => p !== undefined)

  const query = search.trim().toLowerCase()
  const results = query
    ? available.filter((p) => !productIds.includes(p.id) && p.name.toLowerCase().includes(query)).slice(0, 8)
    : []

  const add = (id: string) => {
    if (productIds.length >= MAX_POPUP_PRODUCTS || productIds.includes(id)) return
    onChange([...productIds, id])
    setSearch('')
  }
  const remove = (id: string) => onChange(productIds.filter((pid) => pid !== id))
  const move = (index: number, dir: -1 | 1) => {
    const target = index + dir
    if (target < 0 || target >= productIds.length) return
    const next = [...productIds]
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
  }

  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel}>Featured products (up to {MAX_POPUP_PRODUCTS})</label>

      {selected.length > 0 && (
        <ul className={styles.pickerList}>
          {selected.map((p, i) => (
            <li key={p.id} className={styles.pickerRow}>
              <span className={styles.pickerName}>{p.name}</span>
              <div className={styles.pickerActions}>
                <button
                  type="button"
                  className={styles.pickerBtn}
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                  aria-label={`Move ${p.name} up`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className={styles.pickerBtn}
                  disabled={i === selected.length - 1}
                  onClick={() => move(i, 1)}
                  aria-label={`Move ${p.name} down`}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className={styles.pickerBtn}
                  onClick={() => remove(p.id)}
                  aria-label={`Remove ${p.name}`}
                >
                  ✕
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {productIds.length < MAX_POPUP_PRODUCTS ? (
        <>
          <input
            className={styles.input}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search products to feature…"
          />
          {results.length > 0 && (
            <ul className={styles.pickerList}>
              {results.map((p) => (
                <li key={p.id} className={styles.pickerRow}>
                  <span className={styles.pickerName}>{p.name}</span>
                  <button type="button" className={styles.btnSecondary} onClick={() => add(p.id)}>
                    Add
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className={styles.hint}>Maximum of {MAX_POPUP_PRODUCTS} reached — remove one to add another.</p>
      )}

      <p className={styles.hint}>
        Rendered as product rows in the popup, in this order. Out-of-stock or
        removed items are skipped automatically.
      </p>
    </div>
  )
}

/** admin-listing product → the shape ScanPopupCard's ProductImage/priceLabel
 *  need. Approximation only: the admin product list has no nested variant
 *  rows, so a has_variants product previews its base price rather than the
 *  true minimum variant price. Never affects the real customer popup, which
 *  always resolves against the customer /menu payload's real ProductPublic
 *  data (see Menu.tsx). */
function toPreviewProduct(p: ProductResponse): ProductPublic {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    base_price: p.base_price,
    tax_rate: p.tax_rate,
    food_type: p.food_type,
    image_url: p.image_url,
    has_variants: p.has_variants,
    allows_addons: p.allows_addons,
    variants: [],
    addons: [],
    model_glb_url: null,
    model_usdz_url: null,
  }
}

type PopupFormSlice = Pick<
  SettingsResponse,
  | 'popup_enabled'
  | 'popup_badge_text'
  | 'popup_headline'
  | 'popup_masthead_subline'
  | 'popup_bubble_text'
  | 'popup_kicker'
  | 'popup_tagline'
  | 'popup_section_label'
  | 'popup_cta_text'
  | 'popup_footer_text'
  | 'popup_product_ids'
  | 'menu_accent_color'
>

interface Props {
  form: PopupFormSlice
  onChange: (patch: Partial<PopupFormSlice>) => void
  illustrationUrl: string | null
  restaurantName: string | null
}

export default function ScanPopupSection({ form, onChange, illustrationUrl, restaurantName }: Props) {
  const [previewMode, setPreviewMode] = useState<MenuThemeMode>('light')
  const { data: products } = useListProductsQuery()

  const byId = new Map((products ?? []).map((p) => [p.id, p]))
  const previewProducts: ProductPublic[] = form.popup_product_ids
    .map((id) => byId.get(id))
    .filter((p): p is ProductResponse => p !== undefined)
    .map(toPreviewProduct)

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>Scan popup</h2>
      <label className={styles.toggle}>
        <span className={styles.toggleLabel}>Show popup on first menu open</span>
        <input
          type="checkbox"
          checked={form.popup_enabled}
          onChange={(e) => onChange({ popup_enabled: e.target.checked })}
        />
      </label>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Badge text</label>
        <input
          className={styles.input}
          value={form.popup_badge_text ?? ''}
          onChange={(e) => onChange({ popup_badge_text: e.target.value.slice(0, 30) })}
          maxLength={30}
          placeholder="SPECIAL EDITION"
        />
        <p className={styles.hint}>Small pill in the top corner. Leave blank to hide.</p>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Headline</label>
        <input
          className={styles.input}
          value={form.popup_headline ?? ''}
          onChange={(e) => onChange({ popup_headline: e.target.value.slice(0, 60) })}
          maxLength={60}
          placeholder="Your restaurant name"
        />
        <p className={styles.hint}>Large masthead title. Leave blank to use your restaurant name.</p>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Masthead subline</label>
        <input
          className={styles.input}
          value={form.popup_masthead_subline ?? ''}
          onChange={(e) => onChange({ popup_masthead_subline: e.target.value.slice(0, 80) })}
          maxLength={80}
          placeholder="BREWING MEMORIES · ESTD. 2023 · GOOD NEWS ONLY"
        />
        <p className={styles.hint}>Small line under the headline. Leave blank to hide.</p>
      </div>

      <PopupIllustrationSection illustrationUrl={illustrationUrl} />

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Speech-bubble text</label>
        <input
          className={styles.input}
          value={form.popup_bubble_text ?? ''}
          onChange={(e) => onChange({ popup_bubble_text: e.target.value.slice(0, 100) })}
          maxLength={100}
          placeholder={`"What's new here?"`}
        />
        <p className={styles.hint}>Leave blank to hide the bubble AND the illustration above.</p>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Kicker</label>
        <input
          className={styles.input}
          value={form.popup_kicker ?? ''}
          onChange={(e) => onChange({ popup_kicker: e.target.value.slice(0, 60) })}
          maxLength={60}
          placeholder="WE'VE BEEN BUSY BREWING…"
        />
        <p className={styles.hint}>Short uppercase line. Leave blank to hide.</p>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Tagline</label>
        <input
          className={styles.input}
          value={form.popup_tagline ?? ''}
          onChange={(e) => onChange({ popup_tagline: e.target.value.slice(0, 100) })}
          maxLength={100}
          placeholder="New flavours. Bold bites. Made for you."
        />
        <p className={styles.hint}>Leave blank to hide.</p>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Section label</label>
        <input
          className={styles.input}
          value={form.popup_section_label ?? ''}
          onChange={(e) => onChange({ popup_section_label: e.target.value.slice(0, 40) })}
          maxLength={40}
          placeholder="New arrivals"
        />
        <p className={styles.hint}>Divider above the featured products. Leave blank to use "New arrivals".</p>
      </div>

      <PopupProductPicker
        productIds={form.popup_product_ids}
        onChange={(ids) => onChange({ popup_product_ids: ids })}
      />

      <div className={styles.field}>
        <label className={styles.fieldLabel}>CTA button text</label>
        <input
          className={styles.input}
          value={form.popup_cta_text ?? ''}
          onChange={(e) => onChange({ popup_cta_text: e.target.value.slice(0, 40) })}
          maxLength={40}
          placeholder="See the menu"
        />
        <p className={styles.hint}>Leave blank to use "See the menu".</p>
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Footer text</label>
        <input
          className={styles.input}
          value={form.popup_footer_text ?? ''}
          onChange={(e) => onChange({ popup_footer_text: e.target.value.slice(0, 80) })}
          maxLength={80}
          placeholder="Made fresh · Served hot · Loved always"
        />
        <p className={styles.hint}>Leave blank to hide.</p>
      </div>

      <div className={previewStyles.previewLabelRow}>
        <span className={previewStyles.previewLabel}>Live preview</span>
        <div className={previewStyles.themeToggle} role="radiogroup" aria-label="Preview theme">
          <button
            type="button"
            role="radio"
            aria-checked={previewMode === 'light'}
            className={`${previewStyles.themeToggleBtn} ${previewMode === 'light' ? previewStyles.themeToggleBtnActive : ''}`}
            onClick={() => setPreviewMode('light')}
          >
            Light
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={previewMode === 'dark'}
            className={`${previewStyles.themeToggleBtn} ${previewMode === 'dark' ? previewStyles.themeToggleBtnActive : ''}`}
            onClick={() => setPreviewMode('dark')}
          >
            Dark
          </button>
        </div>
      </div>
      {!form.popup_enabled && (
        <p className={styles.hint}>Popup is off — customers won't see it. Shown below anyway so you can compose it first.</p>
      )}
      {previewProducts.length === 0 && (
        <p className={styles.hint}>Pick products above to see them appear here.</p>
      )}
      {/* stopPropagation in the capture phase neutralises the card's close/CTA
          buttons — this is a preview, not a real modal, and must never
          navigate or dismiss anything on the Menu Design page. */}
      <div
        className={previewStyles.stage}
        data-theme={previewMode}
        style={deriveMenuTheme(form.menu_accent_color, previewMode)}
        onClickCapture={(e) => e.stopPropagation()}
        onKeyDownCapture={(e) => e.stopPropagation()}
      >
        <ScanPopupCard
          variant="preview"
          products={previewProducts}
          restaurantName={restaurantName}
          badgeText={form.popup_badge_text}
          headline={form.popup_headline}
          mastheadSubline={form.popup_masthead_subline}
          bubbleText={form.popup_bubble_text}
          kicker={form.popup_kicker}
          tagline={form.popup_tagline}
          sectionLabel={form.popup_section_label}
          ctaText={form.popup_cta_text}
          footerText={form.popup_footer_text}
          illustrationUrl={illustrationUrl}
          onClose={() => {}}
        />
      </div>
    </section>
  )
}
