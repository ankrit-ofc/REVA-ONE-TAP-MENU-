/**
 * Pure, props-driven content of the scan popup's glass card — every field
 * blank/whitespace rule and fallback (headline → restaurant name, CTA →
 * "See the menu") lives here, so the real customer popup (ScanPopup.tsx) and
 * the admin's live preview (ScanPopupSection.tsx) share identical rendering
 * and blank-hides-element behaviour instead of two copies that can drift.
 *
 * No data fetching here — the caller resolves products and passes every
 * text/illustration field as a prop (raw, untrimmed is fine; this component
 * trims and applies fallbacks itself).
 */
import { X } from 'lucide-react'
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
  restaurantName: string | null
  badgeText: string | null
  headline: string | null
  mastheadSubline: string | null
  bubbleText: string | null
  kicker: string | null
  tagline: string | null
  sectionLabel: string | null
  ctaText: string | null
  footerText: string | null
  illustrationUrl: string | null
  onClose: () => void
  /** 'preview' drops dialog ARIA semantics — a live admin preview isn't a
   *  real modal and shouldn't announce itself as one to screen readers. */
  variant?: 'modal' | 'preview'
}

export default function ScanPopupCard({
  products,
  restaurantName,
  badgeText,
  headline: rawHeadline,
  mastheadSubline,
  bubbleText: rawBubbleText,
  kicker: rawKicker,
  tagline: rawTagline,
  sectionLabel: rawSectionLabel,
  ctaText: rawCtaText,
  footerText,
  illustrationUrl,
  onClose,
  variant = 'modal',
}: Props) {
  const badge = badgeText?.trim()
  const headline = rawHeadline?.trim() || restaurantName || 'Our Menu'
  const subline = mastheadSubline?.trim()
  const bubbleText = rawBubbleText?.trim()
  const kicker = rawKicker?.trim()
  const tagline = rawTagline?.trim()
  const sectionLabel = rawSectionLabel?.trim() || 'New arrivals'
  const ctaText = rawCtaText?.trim() || 'See the menu'
  const footer = footerText?.trim()

  const dialogProps =
    variant === 'modal'
      ? { role: 'dialog' as const, 'aria-modal': true, 'aria-labelledby': 'scan-popup-headline' }
      : {}

  return (
    <div
      className={styles.panel}
      onClick={(e) => e.stopPropagation()}
      {...dialogProps}
    >
      <button className={styles.close} onClick={onClose} aria-label="Close">
        <X size={16} strokeWidth={2} aria-hidden="true" />
      </button>

      <div className={styles.masthead}>
        {badge && <span className={styles.badge}>{badge}</span>}
        <p id="scan-popup-headline" className={styles.headline}>{headline}</p>
        {subline && <p className={styles.subline}>{subline}</p>}
      </div>

      {bubbleText && (
        <div className={styles.bubbleRow}>
          {illustrationUrl && (
            <img src={illustrationUrl} alt="" className={styles.illustration} />
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
      {footer && <p className={styles.footer}>{footer}</p>}
    </div>
  )
}
