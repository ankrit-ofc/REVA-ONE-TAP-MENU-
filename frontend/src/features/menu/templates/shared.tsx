import { useNavigate } from 'react-router-dom'
import { formatPrice } from '@/lib/currency'
import { prefetchModel } from '@/features/ar/modelPrefetch'
import type { FoodTypePublic, ProductPublic } from '@/lib/schemas/menu'
import styles from './shared.module.css'

export const FOOD_LABEL: Record<FoodTypePublic, string> = {
  VEG: 'Veg', NON_VEG: 'Non-veg', EGG: 'Egg', BEVERAGE: 'Beverage', SMOKE: 'Smoke',
}
const VEG_CLASS: Record<FoodTypePublic, string> = {
  VEG: styles.vegVeg, NON_VEG: styles.vegNonVeg, EGG: styles.vegEgg,
  BEVERAGE: styles.vegBeverage, SMOKE: styles.vegSmoke,
}

/** Tap-anywhere-to-open + AR warm-prefetch, shared by every template's card. */
export function useProductOpen(product: ProductPublic) {
  const navigate = useNavigate()
  const open = () => navigate(`/product/${product.id}`)
  return {
    role: 'button' as const,
    tabIndex: 0,
    onClick: open,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() }
    },
    onPointerDown: () => { if (product.model_glb_url) prefetchModel(product.model_glb_url) },
  }
}

export function priceLabel(product: ProductPublic, currency: string): string {
  const minVariant = product.variants.length > 0
    ? Math.min(...product.variants.map((v) => v.price))
    : product.base_price
  return product.has_variants ? `from ${formatPrice(minVariant, currency)}` : formatPrice(product.base_price, currency)
}

/** Small square/round veg-nonveg-egg indicator (India-standard). */
export function VegDot({ foodType }: { foodType: FoodTypePublic }) {
  return (
    <span
      className={`${styles.veg} ${VEG_CLASS[foodType] ?? styles.vegNonVeg}`}
      title={FOOD_LABEL[foodType]}
      aria-label={FOOD_LABEL[foodType]}
    >
      <span className={styles.vegInnerDot} />
    </span>
  )
}

/** Product image, or a sensible fallback (every template needs one — items
 *  without a photo are common, especially on 200+ item menus). */
export function ProductImage({ product, className }: { product: ProductPublic; className: string }) {
  return product.image_url
    ? <img className={className} src={product.image_url} alt={product.name} loading="lazy" />
    : <div className={`${className} ${styles.imgPlaceholder}`} aria-hidden="true">🍽️</div>
}

/** Round accent "open" affordance — the explicit tappable button each template
 *  carries in addition to whole-card tap (parity with the old chevron). Purely
 *  decorative: the card itself carries the accessible name via aria-label. */
export function OpenButton() {
  return (
    <span className={styles.openBtn} aria-hidden="true">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
        strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 6l6 6-6 6" />
      </svg>
    </span>
  )
}
