import type { ProductPublic } from '@/lib/schemas/menu'
import { OpenButton, ProductImage, VegDot, priceLabel, useProductOpen } from './shared'
import styles from './PhotoGridTemplate.module.css'

/** Two-column cards, large images — the default template. */
export default function PhotoGridTemplate({ products, currency }: { products: ProductPublic[]; currency: string }) {
  return (
    <div className={styles.grid}>
      {products.map((p) => <Card key={p.id} product={p} currency={currency} />)}
    </div>
  )
}

function Card({ product, currency }: { product: ProductPublic; currency: string }) {
  const tap = useProductOpen(product)
  return (
    <div className={styles.card} {...tap} aria-label={`${product.name}, ${priceLabel(product, currency)}`}>
      <ProductImage product={product} className={styles.image} />
      <div className={styles.body}>
        <div className={styles.nameRow}>
          <VegDot foodType={product.food_type} />
          <span className={styles.name}>{product.name}</span>
        </div>
        {product.description && <p className={styles.description}>{product.description}</p>}
        <div className={styles.footer}>
          <span className={styles.price}>{priceLabel(product, currency)}</span>
          <OpenButton />
        </div>
      </div>
    </div>
  )
}
