import { useNavigate } from 'react-router-dom'
import { formatPrice } from '@/lib/currency'
import { prefetchModel } from '@/features/ar/modelPrefetch'
import type { ProductPublic, FoodTypePublic } from '@/lib/schemas/menu'
import styles from './ProductCard.module.css'

const FOOD_LABEL: Record<FoodTypePublic, string> = {
  VEG: 'Veg', NON_VEG: 'Non-veg', EGG: 'Egg', BEVERAGE: 'Beverage', SMOKE: 'Smoke',
}
const VEG_CLASS: Record<FoodTypePublic, string> = {
  VEG: styles.vegVeg, NON_VEG: styles.vegNonVeg, EGG: styles.vegEgg,
  BEVERAGE: styles.vegBeverage, SMOKE: styles.vegSmoke,
}

interface Props {
  product: ProductPublic
  currency: string
}

/**
 * Menu row (display only). Tapping anywhere on the card opens the product detail
 * page, where the customer picks variants/add-ons, adds to cart, and views the dish
 * in AR. The tap also warms the AR model so the detail page is ready to launch fast.
 */
export default function ProductCard({ product, currency }: Props) {
  const navigate = useNavigate()

  const minVariant = product.variants.length > 0
    ? Math.min(...product.variants.map((v) => v.price))
    : product.base_price
  const priceLabel = product.has_variants
    ? `from ${formatPrice(minVariant, currency)}`
    : formatPrice(product.base_price, currency)

  const vegClass = VEG_CLASS[product.food_type] ?? styles.vegNonVeg

  const open = () => navigate(`/product/${product.id}`)

  return (
    <div
      className={styles.card}
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() }
      }}
      onPointerDown={() => { if (product.model_glb_url) prefetchModel(product.model_glb_url) }}
      aria-label={`${product.name}, ${priceLabel}`}
      style={{ cursor: 'pointer' }}
    >
      <div className={styles.row}>
        <div className={styles.thumbWrap}>
          {product.image_url
            ? <img className={styles.thumb} src={product.image_url} alt={product.name} loading="lazy" />
            : <div className={styles.thumbPlaceholder} aria-hidden>🍽️</div>}
        </div>

        <div className={styles.info}>
          <div className={styles.nameRow}>
            <span className={`${styles.veg} ${vegClass}`} title={FOOD_LABEL[product.food_type]} aria-label={FOOD_LABEL[product.food_type]}>
              <span className={styles.vegDot} />
            </span>
            <span className={styles.name}>{product.name}</span>
          </div>
          {product.description && <span className={styles.description}>{product.description}</span>}

          <div className={styles.priceRow}>
            <span className={styles.price}>{priceLabel}</span>
            <span className={styles.chevron} aria-hidden>›</span>
          </div>
        </div>
      </div>
    </div>
  )
}
