import { useState, useEffect, useRef } from 'react'
import {
  useGetSettingsQuery,
  useUpdateSettingsMutation,
  useUploadBannerImageMutation,
  useRemoveBannerImageMutation,
  useUploadPopupIllustrationMutation,
  useRemovePopupIllustrationMutation,
  useListProductsQuery,
} from '@/features/admin/adminApi'
import type { ProductResponse, SettingsResponse, SettingsUpdate } from '@/lib/schemas/admin'
import { HEX_COLOR_PATTERN } from '@/lib/schemas/menu'
import MenuThemeSection from './MenuThemeSection'
import styles from './Settings.module.css'

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Save failed'
}

type MenuDesignForm = Pick<
  SettingsResponse,
  | 'menu_template'
  | 'menu_accent_color'
  | 'specials_section_title'
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
>

const BANNER_MAX_MB = 25
const BANNER_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Menu hero banner: upload with preview, replace, remove. Uploads apply
 *  immediately (the backend validates content, size, and dimensions).
 *  Also hosts the "Today's Special" section title — saved with the rest of
 *  the form via the "Save Settings" button below, not applied immediately. */
function BannerSection({
  bannerUrl,
  specialsSectionTitle,
  onSpecialsSectionTitleChange,
}: {
  bannerUrl: string | null
  specialsSectionTitle: string | null
  onSpecialsSectionTitleChange: (value: string) => void
}) {
  const [upload, { isLoading: uploading }] = useUploadBannerImageMutation()
  const [remove, { isLoading: removing }] = useRemoveBannerImageMutation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState<string | null>(null)

  const pick = async (file: File) => {
    setErr(null)
    if (!BANNER_TYPES.includes(file.type)) { setErr('Only JPEG, PNG, or WebP images allowed.'); return }
    if (file.size > BANNER_MAX_MB * 1024 * 1024) { setErr(`Image must be under ${BANNER_MAX_MB} MB.`); return }
    try {
      await upload(file).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  return (
    <section className={`${styles.section} ${styles.bannerSection}`}>
      <h2 className={styles.sectionTitle}>Menu banner</h2>
      <div className={styles.field}>
        {bannerUrl
          ? <img src={bannerUrl} alt="Current menu banner" className={styles.bannerPreview} />
          : <div className={styles.bannerEmpty}>No banner uploaded — the menu shows the stock photo.</div>}
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) void pick(f)
            e.target.value = '' // allow re-selecting the same file
          }}
        />
        <div className={styles.bannerActions}>
          <button
            type="button"
            className={styles.btnSecondary}
            disabled={uploading || removing}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? 'Uploading…' : bannerUrl ? 'Replace banner' : 'Upload banner'}
          </button>
          {bannerUrl && (
            <button
              type="button"
              className={styles.btnSecondary}
              disabled={uploading || removing}
              onClick={() => { setErr(null); void remove() }}
            >
              {removing ? 'Removing…' : 'Remove banner'}
            </button>
          )}
        </div>
        {err && <p className={styles.geoErr}>{err}</p>}
        <p className={styles.hint}>
          Shown as the hero photo on the customer menu. JPEG, PNG, or WebP up to
          {' '}{BANNER_MAX_MB} MB and at most 2400×1200 px — a wide landscape image works best.
        </p>
      </div>
      <div className={styles.field}>
        <label className={styles.fieldLabel}>Specials section title</label>
        <input
          className={styles.input}
          value={specialsSectionTitle ?? ''}
          onChange={(e) => onSpecialsSectionTitleChange(e.target.value.slice(0, 80))}
          maxLength={80}
          placeholder="Today's Special"
        />
        <p className={styles.hint}>
          Heading shown above the featured dishes on the customer menu. Leave blank
          to use the default "Today's Special". Saved with the button below.
        </p>
      </div>
    </section>
  )
}

const ILLUSTRATION_MAX_MB = 25
const ILLUSTRATION_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Scan-popup illustration: upload with preview, replace, remove. Uploads
 *  apply immediately, mirroring BannerSection's image upload exactly. */
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

export default function AdminMenuDesign() {
  const { data: settings, isLoading, isError } = useGetSettingsQuery()
  const [update, { isLoading: isSaving }] = useUpdateSettingsMutation()

  const [form, setForm] = useState<MenuDesignForm | null>(null)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (settings) {
      setForm({
        menu_template: settings.menu_template,
        menu_accent_color: settings.menu_accent_color,
        specials_section_title: settings.specials_section_title,
        popup_enabled: settings.popup_enabled,
        popup_badge_text: settings.popup_badge_text,
        popup_headline: settings.popup_headline,
        popup_masthead_subline: settings.popup_masthead_subline,
        popup_bubble_text: settings.popup_bubble_text,
        popup_kicker: settings.popup_kicker,
        popup_tagline: settings.popup_tagline,
        popup_section_label: settings.popup_section_label,
        popup_cta_text: settings.popup_cta_text,
        popup_footer_text: settings.popup_footer_text,
        popup_product_ids: settings.popup_product_ids,
      })
    }
  }, [settings])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form) return
    setErr(null)
    setSaved(false)
    if (form.menu_accent_color && !HEX_COLOR_PATTERN.test(form.menu_accent_color)) {
      setErr('Accent colour must be a hex code like #1D9E75.')
      return
    }

    const payload: SettingsUpdate = {
      menu_template: form.menu_template,
      menu_accent_color: form.menu_accent_color ?? undefined,
      // Always sent (trimmed); backend normalizes whitespace-only to NULL,
      // which is how each field is cleared back to its default/hidden state.
      specials_section_title: (form.specials_section_title ?? '').trim(),
      popup_enabled: form.popup_enabled,
      popup_badge_text: (form.popup_badge_text ?? '').trim(),
      popup_headline: (form.popup_headline ?? '').trim(),
      popup_masthead_subline: (form.popup_masthead_subline ?? '').trim(),
      popup_bubble_text: (form.popup_bubble_text ?? '').trim(),
      popup_kicker: (form.popup_kicker ?? '').trim(),
      popup_tagline: (form.popup_tagline ?? '').trim(),
      popup_section_label: (form.popup_section_label ?? '').trim(),
      popup_cta_text: (form.popup_cta_text ?? '').trim(),
      popup_footer_text: (form.popup_footer_text ?? '').trim(),
      popup_product_ids: form.popup_product_ids,
    }
    try {
      await update(payload).unwrap()
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  if (isLoading) return <div className={styles.state}>Loading settings…</div>
  if (isError || !form) return <div className={styles.state} style={{ color: '#dc2626' }}>Failed to load settings.</div>

  return (
    <div className={styles.root}>
      <h1 className={styles.title}>Menu Design</h1>

      <BannerSection
        bannerUrl={settings?.banner_image_url ?? null}
        specialsSectionTitle={form.specials_section_title}
        onSpecialsSectionTitleChange={(v) => setForm({ ...form, specials_section_title: v })}
      />

      <form onSubmit={(e) => void handleSubmit(e)} className={styles.form}>
        <MenuThemeSection
          template={form.menu_template}
          accentColor={form.menu_accent_color}
          onTemplateChange={(t) => setForm({ ...form, menu_template: t })}
          onAccentColorChange={(c) => setForm({ ...form, menu_accent_color: c })}
        />

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Scan popup</h2>
          <label className={styles.toggle}>
            <span className={styles.toggleLabel}>Show popup on first menu open</span>
            <input
              type="checkbox"
              checked={form.popup_enabled}
              onChange={(e) => setForm({ ...form, popup_enabled: e.target.checked })}
            />
          </label>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Badge text</label>
            <input
              className={styles.input}
              value={form.popup_badge_text ?? ''}
              onChange={(e) => setForm({ ...form, popup_badge_text: e.target.value.slice(0, 30) })}
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
              onChange={(e) => setForm({ ...form, popup_headline: e.target.value.slice(0, 60) })}
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
              onChange={(e) => setForm({ ...form, popup_masthead_subline: e.target.value.slice(0, 80) })}
              maxLength={80}
              placeholder="BREWING MEMORIES · ESTD. 2023 · GOOD NEWS ONLY"
            />
            <p className={styles.hint}>Small line under the headline. Leave blank to hide.</p>
          </div>

          <PopupIllustrationSection illustrationUrl={settings?.popup_illustration_url ?? null} />

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Speech-bubble text</label>
            <input
              className={styles.input}
              value={form.popup_bubble_text ?? ''}
              onChange={(e) => setForm({ ...form, popup_bubble_text: e.target.value.slice(0, 100) })}
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
              onChange={(e) => setForm({ ...form, popup_kicker: e.target.value.slice(0, 60) })}
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
              onChange={(e) => setForm({ ...form, popup_tagline: e.target.value.slice(0, 100) })}
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
              onChange={(e) => setForm({ ...form, popup_section_label: e.target.value.slice(0, 40) })}
              maxLength={40}
              placeholder="New arrivals"
            />
            <p className={styles.hint}>Divider above the featured products. Leave blank to use "New arrivals".</p>
          </div>

          <PopupProductPicker
            productIds={form.popup_product_ids}
            onChange={(ids) => setForm({ ...form, popup_product_ids: ids })}
          />

          <div className={styles.field}>
            <label className={styles.fieldLabel}>CTA button text</label>
            <input
              className={styles.input}
              value={form.popup_cta_text ?? ''}
              onChange={(e) => setForm({ ...form, popup_cta_text: e.target.value.slice(0, 40) })}
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
              onChange={(e) => setForm({ ...form, popup_footer_text: e.target.value.slice(0, 80) })}
              maxLength={80}
              placeholder="Made fresh · Served hot · Loved always"
            />
            <p className={styles.hint}>Leave blank to hide.</p>
          </div>
        </section>

        {err && <p className={styles.err}>{err}</p>}
        {saved && <p className={styles.saved}>Settings saved ✓</p>}

        <button type="submit" className={styles.btnSave} disabled={isSaving}>
          {isSaving ? 'Saving…' : 'Save Settings'}
        </button>
      </form>
    </div>
  )
}
