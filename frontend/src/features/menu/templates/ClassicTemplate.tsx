import type { FoodTypePublic, ProductPublic } from '@/lib/schemas/menu'
import { FOOD_LABEL, priceLabel, useProductOpen } from './shared'
import styles from './ClassicTemplate.module.css'

const VEG_CLASS: Record<FoodTypePublic, string> = {
  VEG: styles.vegVeg, NON_VEG: styles.vegNonVeg, EGG: styles.vegEgg,
  BEVERAGE: styles.vegBeverage, SMOKE: styles.vegSmoke,
}

/**
 * Today's default menu row — a faithful port of the original ProductCard.
 * This is what every restaurant renders until an admin opts into a
 * different template, so its markup and CSS intentionally mirror the
 * pre-theming component 1:1 (own veg-dot/placeholder styling rather than
 * the shared templates/shared.tsx bits, which were tuned for the other
 * five templates and are NOT pixel-identical to this one).
 */
export default function ClassicTemplate({ products, currency }: { products: ProductPublic[]; currency: string }) {
  return (
    <div className={styles.list}>
      {products.map((p) => <Card key={p.id} product={p} currency={currency} />)}
    </div>
  )
}

function Card({ product, currency }: { product: ProductPublic; currency: string }) {
  const tap = useProductOpen(product)
  const vegClass = VEG_CLASS[product.food_type] ?? styles.vegNonVeg
  const label = priceLabel(product, currency)

  return (
    <div
      className={styles.card}
      {...tap}
      aria-label={`${product.name}, ${label}`}
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
            <span className={styles.price}>{label}</span>
            <span className={styles.chevron} aria-hidden>›</span>
          </div>
        </div>
      </div>
    </div>
  )
}
