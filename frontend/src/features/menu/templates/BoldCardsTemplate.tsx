import type { ProductPublic } from '@/lib/schemas/menu'
import { OpenButton, ProductImage, VegDot, priceLabel, useProductOpen } from './shared'
import styles from './BoldCardsTemplate.module.css'

/** Full-width cards with the accent colour as a tinted background block. */
export default function BoldCardsTemplate({ products, currency }: { products: ProductPublic[]; currency: string }) {
  return (
    <div className={styles.list}>
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
          <span className={styles.viewBtn}>
            View <OpenButton />
          </span>
        </div>
      </div>
    </div>
  )
}
