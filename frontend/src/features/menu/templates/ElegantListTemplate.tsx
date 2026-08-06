import type { ProductPublic } from '@/lib/schemas/menu'
import { VegDot, priceLabel, useProductOpen } from './shared'
import styles from './ElegantListTemplate.module.css'

/** Serif, no photos — name and price on one line, generous spacing. */
export default function ElegantListTemplate({ products, currency }: { products: ProductPublic[]; currency: string }) {
  return (
    <div className={styles.list}>
      {products.map((p) => <Row key={p.id} product={p} currency={currency} />)}
    </div>
  )
}

function Row({ product, currency }: { product: ProductPublic; currency: string }) {
  const tap = useProductOpen(product)
  return (
    <div className={styles.row} {...tap} aria-label={`${product.name}, ${priceLabel(product, currency)}`}>
      <div className={styles.headline}>
        <span className={styles.nameWrap}>
          <VegDot foodType={product.food_type} />
          <span className={styles.name}>{product.name}</span>
        </span>
        <span className={styles.dots} aria-hidden="true" />
        <span className={styles.price}>{priceLabel(product, currency)}</span>
      </div>
      {product.description && <p className={styles.description}>{product.description}</p>}
    </div>
  )
}
