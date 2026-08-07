/**
 * Promotional popup shown once per table session, on first menu load.
 * Newspaper-styled "glass" card over the dimmed menu — structurally mirrors
 * CustomerLayout's infoOverlay/infoPanel (backdrop dismiss, stopPropagation
 * panel, role=dialog), styled per design/chiya_times_newspaper_popup_mockup.html.
 *
 * Every piece of copy is admin-editable (Menu Design → "Scan popup") and
 * blank/whitespace hides that element entirely, except headline (falls back
 * to the restaurant name) and the CTA (falls back to "See the menu") — never
 * an empty gap. The caller passes an already-resolved, non-empty product
 * list (see Menu.tsx's mount gate); this component does not fetch or filter.
 */
import { X } from 'lucide-react'
import { useMenu } from '@/features/menu/useMenu'
import { useSession } from '@/features/session/useSession'
import { ProductImage, priceLabel } from '@/features/menu/templates/shared'
import type { ProductPublic } from '@/lib/schemas/menu'
import styles from './ScanPopup.module.css'

const CURRENCY = 'NPR'
const DESCRIPTION_MAX = 60

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1).trimEnd()}…`
}

interface Props {
  products: ProductPublic[]
  onClose: () => void
}

export default function ScanPopup({ products, onClose }: Props) {
  const { restaurantName } = useSession()
  const {
    popupBadgeText,
    popupHeadline,
    popupMastheadSubline,
    popupBubbleText,
    popupKicker,
    popupTagline,
    popupSectionLabel,
    popupCtaText,
    popupFooterText,
    popupIllustrationUrl,
  } = useMenu()

  const badgeText = popupBadgeText?.trim()
  const headline = popupHeadline?.trim() || restaurantName || 'Our Menu'
  const mastheadSubline = popupMastheadSubline?.trim()
  const bubbleText = popupBubbleText?.trim()
  const kicker = popupKicker?.trim()
  const tagline = popupTagline?.trim()
  const sectionLabel = popupSectionLabel?.trim() || 'New arrivals'
  const ctaText = popupCtaText?.trim() || 'See the menu'
  const footerText = popupFooterText?.trim()

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <div
        className={styles.panel}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="scan-popup-headline"
      >
        <button className={styles.close} onClick={onClose} aria-label="Close">
          <X size={16} strokeWidth={2} aria-hidden="true" />
        </button>

        <div className={styles.masthead}>
          {badgeText && <span className={styles.badge}>{badgeText}</span>}
          <p id="scan-popup-headline" className={styles.headline}>{headline}</p>
          {mastheadSubline && <p className={styles.subline}>{mastheadSubline}</p>}
        </div>

        {bubbleText && (
          <div className={styles.bubbleRow}>
            {popupIllustrationUrl && (
              <img src={popupIllustrationUrl} alt="" className={styles.illustration} />
            )}
            <div className={styles.bubble}>
              <p className={styles.bubbleText}>{bubbleText}</p>
            </div>
          </div>
        )}

        {kicker && <p className={styles.kicker}>{kicker}</p>}
        {tagline && <p className={styles.tagline}>{tagline}</p>}

        <div className={styles.divider}>
          <p className={styles.dividerLabel}>★ {sectionLabel} ★</p>
        </div>

        <div className={styles.products}>
          {products.map((p) => (
            <div key={p.id} className={styles.productRow}>
              <ProductImage product={p} className={styles.productImg} />
              <div className={styles.productInfo}>
                <p className={styles.productName}>{p.name}</p>
                {p.description && (
                  <p className={styles.productDesc}>{truncate(p.description, DESCRIPTION_MAX)}</p>
                )}
              </div>
              <span className={styles.priceChip}>{priceLabel(p, CURRENCY)}</span>
            </div>
          ))}
        </div>

        <button className={styles.cta} onClick={onClose}>{ctaText}</button>
        {footerText && <p className={styles.footer}>{footerText}</p>}
      </div>
    </div>
  )
}
