import { useState, useEffect, useRef } from 'react'
import {
  useGetSettingsQuery,
  useUpdateSettingsMutation,
  useUploadBannerImageMutation,
  useRemoveBannerImageMutation,
} from '@/features/admin/adminApi'
import { useGetMeQuery } from '@/features/auth/authApi'
import type { SettingsResponse, SettingsUpdate } from '@/lib/schemas/admin'
import { HEX_COLOR_PATTERN } from '@/lib/schemas/menu'
import MenuThemeSection from './MenuThemeSection'
import ScanPopupSection from './ScanPopupSection'
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

export default function AdminMenuDesign() {
  const { data: settings, isLoading, isError } = useGetSettingsQuery()
  const { data: me } = useGetMeQuery()
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

        <ScanPopupSection
          form={form}
          onChange={(patch) => setForm({ ...form, ...patch })}
          illustrationUrl={settings?.popup_illustration_url ?? null}
          restaurantName={me?.restaurant_name ?? null}
        />

        {err && <p className={styles.err}>{err}</p>}
        {saved && <p className={styles.saved}>Settings saved ✓</p>}

        <button type="submit" className={styles.btnSave} disabled={isSaving}>
          {isSaving ? 'Saving…' : 'Save Settings'}
        </button>
      </form>
    </div>
  )
}
