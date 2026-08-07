import { useState, useEffect, useRef } from 'react'
import {
  useGetSettingsQuery,
  useUpdateSettingsMutation,
  useUploadBannerImageMutation,
  useRemoveBannerImageMutation,
  useUploadPaymentQrMutation,
  useRemovePaymentQrMutation,
} from '@/features/admin/adminApi'
import type { SettingsResponse, SettingsUpdate } from '@/lib/schemas/admin'
import { HEX_COLOR_PATTERN } from '@/lib/schemas/menu'
import { getDevicePosition, GeolocationError } from '@/lib/geolocation'
import MenuThemeSection from './MenuThemeSection'
import styles from './Settings.module.css'

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Save failed'
}

function geoMessage(e: unknown): string {
  if (e instanceof GeolocationError) {
    switch (e.kind) {
      case 'denied':
        return 'Location permission was blocked. Allow location for this site and try again.'
      case 'insecure':
        return 'Capturing location needs a secure (https) connection.'
      case 'unsupported':
        return "This browser can't share location."
      case 'timeout':
        return 'Timed out getting a location fix. Try again.'
      default:
        return 'Could not determine your location. Try again.'
    }
  }
  return 'Could not get your location.'
}

type SettingsForm = Omit<
  SettingsResponse,
  'id' | 'restaurant_id' | 'ar_enabled' | 'qr_pay_enabled'
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

const QR_MAX_MB = 25
const QR_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Payment QR: upload with preview, replace, remove. Mirrors BannerSection —
 *  uploads apply immediately and the backend validates content, size, and
 *  dimensions (the QR is stored uncropped and lossless so it stays scannable). */
function PaymentQrSection({ qrUrl }: { qrUrl: string | null }) {
  const [upload, { isLoading: uploading }] = useUploadPaymentQrMutation()
  const [remove, { isLoading: removing }] = useRemovePaymentQrMutation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState<string | null>(null)

  const pick = async (file: File) => {
    setErr(null)
    if (!QR_TYPES.includes(file.type)) { setErr('Only JPEG, PNG, or WebP images allowed.'); return }
    if (file.size > QR_MAX_MB * 1024 * 1024) { setErr(`Image must be under ${QR_MAX_MB} MB.`); return }
    try {
      await upload(file).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  return (
    <section className={`${styles.section} ${styles.bannerSection}`}>
      <h2 className={styles.sectionTitle}>Payment QR</h2>
      <div className={styles.field}>
        {qrUrl
          ? <img src={qrUrl} alt="Current payment QR" className={styles.bannerPreview} />
          : <div className={styles.bannerEmpty}>No payment QR uploaded — the Billing screen shows none.</div>}
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
            {uploading ? 'Uploading…' : qrUrl ? 'Replace QR' : 'Upload QR'}
          </button>
          {qrUrl && (
            <button
              type="button"
              className={styles.btnSecondary}
              disabled={uploading || removing}
              onClick={() => { setErr(null); void remove() }}
            >
              {removing ? 'Removing…' : 'Remove QR'}
            </button>
          )}
        </div>
        {err && <p className={styles.geoErr}>{err}</p>}
        <p className={styles.hint}>
          Shown to guests on the staff Billing screen so they can scan to pay
          (eSewa / Khalti / Fonepay). JPEG, PNG, or WebP up to {QR_MAX_MB} MB and
          at most 1200×1200 px. Upload the QR uncropped — it is stored without
          cropping or compression so it stays scannable.
        </p>
      </div>
    </section>
  )
}

export default function AdminSettings() {
  const { data: settings, isLoading, isError } = useGetSettingsQuery()
  const [update, { isLoading: isSaving }] = useUpdateSettingsMutation()

  const [form, setForm] = useState<SettingsForm | null>(null)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [geoBusy, setGeoBusy] = useState(false)
  const [geoErr, setGeoErr] = useState<string | null>(null)

  useEffect(() => {
    if (settings) {
      setForm({
        waiter_can_accept_payment: settings.waiter_can_accept_payment,
        allow_order_reopen: settings.allow_order_reopen,
        require_order_approval: settings.require_order_approval,
        currency: settings.currency,
        timezone: settings.timezone,
        require_location: settings.require_location,
        latitude: settings.latitude,
        longitude: settings.longitude,
        geofence_radius_meters: settings.geofence_radius_meters,
        // Printer config is managed on the Devices page; carried here only to
        // satisfy the form type (not edited or sent by this page).
        print_kot_enabled: settings.print_kot_enabled,
        print_bill_enabled: settings.print_bill_enabled,
        bill_copies: settings.bill_copies,
        kot_print_mode: settings.kot_print_mode,
        kot_printer_name: settings.kot_printer_name,
        kot_worker_token: settings.kot_worker_token,
        // Managed by the banner / payment-QR upload/remove endpoints below,
        // not this form.
        banner_image_url: settings.banner_image_url,
        payment_qr_url: settings.payment_qr_url,
        menu_template: settings.menu_template,
        menu_accent_color: settings.menu_accent_color,
        specials_section_title: settings.specials_section_title,
      })
    }
  }, [settings])

  const captureLocation = async () => {
    setGeoErr(null)
    setGeoBusy(true)
    try {
      const pos = await getDevicePosition()
      setForm((f) => (f ? { ...f, latitude: pos.latitude, longitude: pos.longitude } : f))
    } catch (e) {
      setGeoErr(geoMessage(e))
    } finally {
      setGeoBusy(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form) return
    setErr(null)
    setSaved(false)
    if (form.currency.length !== 3) { setErr('Currency must be exactly 3 characters (e.g. NPR).'); return }
    if (!form.timezone.trim()) { setErr('Timezone is required.'); return }
    if (form.require_location && (form.latitude === null || form.longitude === null)) {
      setErr('Capture the restaurant location before requiring location to order.')
      return
    }
    if (!(form.geofence_radius_meters > 0)) { setErr('Radius must be greater than 0.'); return }
    if (form.menu_accent_color && !HEX_COLOR_PATTERN.test(form.menu_accent_color)) {
      setErr('Accent colour must be a hex code like #1D9E75.')
      return
    }

    // Convert nulls → undefined for the optional update fields.
    const payload: SettingsUpdate = {
      waiter_can_accept_payment: form.waiter_can_accept_payment,
      allow_order_reopen: form.allow_order_reopen,
      require_order_approval: form.require_order_approval,
      currency: form.currency,
      timezone: form.timezone,
      require_location: form.require_location,
      latitude: form.latitude ?? undefined,
      longitude: form.longitude ?? undefined,
      geofence_radius_meters: form.geofence_radius_meters,
      menu_template: form.menu_template,
      menu_accent_color: form.menu_accent_color ?? undefined,
      // Always sent (trimmed); backend normalizes whitespace-only to NULL,
      // which is how the field is cleared back to the default title.
      specials_section_title: (form.specials_section_title ?? '').trim(),
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

  const hasPoint = form.latitude !== null && form.longitude !== null

  return (
    <div className={styles.root}>
      <h1 className={styles.title}>Restaurant Settings</h1>

      <BannerSection
        bannerUrl={settings?.banner_image_url ?? null}
        specialsSectionTitle={form.specials_section_title}
        onSpecialsSectionTitleChange={(v) => setForm({ ...form, specials_section_title: v })}
      />
      <PaymentQrSection qrUrl={settings?.payment_qr_url ?? null} />

      <form onSubmit={(e) => void handleSubmit(e)} className={styles.form}>
        <MenuThemeSection
          template={form.menu_template}
          accentColor={form.menu_accent_color}
          onTemplateChange={(t) => setForm({ ...form, menu_template: t })}
          onAccentColorChange={(c) => setForm({ ...form, menu_accent_color: c })}
        />

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Payments</h2>
          {settings?.qr_pay_enabled === false && (
            <p className={styles.hint}>
              Online QR payment is off for this restaurant (set by platform / plan).
            </p>
          )}
          {settings?.qr_pay_enabled === true && (
            <p className={styles.hint}>
              Online QR payment is on (platform-controlled). Guests can pay via eSewa / Khalti / Fonepay when an invoice is pending.
            </p>
          )}
          <label className={styles.toggle}>
            <span className={styles.toggleLabel}>Waiter can accept payment</span>
            <input
              type="checkbox"
              checked={form.waiter_can_accept_payment}
              onChange={(e) => setForm({ ...form, waiter_can_accept_payment: e.target.checked })}
            />
          </label>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Orders</h2>
          <label className={styles.toggle}>
            <span className={styles.toggleLabel}>Allow order reopen (waiter/counter)</span>
            <input
              type="checkbox"
              checked={form.allow_order_reopen}
              onChange={(e) => setForm({ ...form, allow_order_reopen: e.target.checked })}
            />
          </label>
          <label className={styles.toggle}>
            <span className={styles.toggleLabel}>Require waiter approval for orders</span>
            <input
              type="checkbox"
              checked={form.require_order_approval}
              onChange={(e) => setForm({ ...form, require_order_approval: e.target.checked })}
            />
          </label>
          <p className={styles.hint}>
            When on, each batch of items a customer orders waits for a waiter to
            approve it before the kitchen sees it or a KOT prints.
          </p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Location-based ordering</h2>
          <label className={styles.toggle}>
            <span className={styles.toggleLabel}>Require customers to be at the restaurant</span>
            <input
              type="checkbox"
              checked={form.require_location}
              onChange={(e) => setForm({ ...form, require_location: e.target.checked })}
            />
          </label>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Restaurant location</label>
            <div className={hasPoint ? styles.coords : `${styles.coords} ${styles.coordsEmpty}`}>
              {hasPoint
                ? `${form.latitude!.toFixed(6)}, ${form.longitude!.toFixed(6)}`
                : 'Not set'}
            </div>
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={() => void captureLocation()}
              disabled={geoBusy}
            >
              {geoBusy ? 'Getting location…' : hasPoint ? 'Update location' : 'Use my current location'}
            </button>
            {geoErr && <p className={styles.geoErr}>{geoErr}</p>}
            <p className={styles.hint}>
              Stand inside the restaurant and tap the button to capture its coordinates from this
              device. Tap again any time to re-capture.
            </p>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Allowed radius (metres)</label>
            <input
              className={styles.input}
              type="number"
              min={1}
              max={100000}
              value={form.geofence_radius_meters}
              onChange={(e) =>
                setForm({ ...form, geofence_radius_meters: Number(e.target.value) })
              }
            />
            <p className={styles.hint}>
              Customers farther than this from the restaurant can’t start ordering. 50 m suits most
              venues; indoor GPS can be off by tens of metres.
            </p>
          </div>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Locale</h2>
          <div className={styles.field}>
            <label className={styles.fieldLabel}>Currency Code (3 letters)</label>
            <input
              className={styles.input}
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase().slice(0, 3) })}
              maxLength={3}
              placeholder="NPR"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.fieldLabel}>Timezone</label>
            <input
              className={styles.input}
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value.slice(0, 100) })}
              maxLength={100}
              placeholder="Asia/Kathmandu"
            />
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
