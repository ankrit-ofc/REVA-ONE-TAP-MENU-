/**
 * Promotional popup shown once per table session, on first menu load.
 * Newspaper-styled "glass" card over the dimmed menu — structurally mirrors
 * CustomerLayout's infoOverlay/infoPanel (backdrop dismiss, stopPropagation
 * panel, role=dialog), styled per design/chiya_times_newspaper_popup_mockup.html.
 *
 * Every piece of copy is admin-editable (Menu Design → "Scan popup") and
 * blank/whitespace hides that element entirely, except headline (falls back
 * to the restaurant name) and the CTA (falls back to "See the menu") — never
 * an empty gap. That logic lives in ScanPopupCard, shared with the admin's
 * live preview so the two never drift. This component's only job is
 * fetching the real values and rendering the fixed, dismissible overlay.
 *
 * The caller passes an already-resolved, non-empty product list (see
 * Menu.tsx's mount gate); this component does not fetch or filter products.
 */
import { useMenu } from '@/features/menu/useMenu'
import { useSession } from '@/features/session/useSession'
import ScanPopupCard from './ScanPopupCard'
import type { ProductPublic } from '@/lib/schemas/menu'
import styles from './ScanPopup.module.css'

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

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <ScanPopupCard
        products={products}
        restaurantName={restaurantName}
        badgeText={popupBadgeText}
        headline={popupHeadline}
        mastheadSubline={popupMastheadSubline}
        bubbleText={popupBubbleText}
        kicker={popupKicker}
        tagline={popupTagline}
        sectionLabel={popupSectionLabel}
        ctaText={popupCtaText}
        footerText={popupFooterText}
        illustrationUrl={popupIllustrationUrl}
        onClose={onClose}
      />
    </div>
  )
}
