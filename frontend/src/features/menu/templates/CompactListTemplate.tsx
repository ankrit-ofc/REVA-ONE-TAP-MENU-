import type { ProductPublic } from '@/lib/schemas/menu'
import { ProductImage, VegDot, priceLabel, useProductOpen } from './shared'
import styles from './CompactListTemplate.module.css'

/** Tiny thumbnail, name, price. Flat, borderless rows — genuinely denser than
 *  classic, built for menus with 200+ items where every extra pixel of row
 *  height costs scrolling. */
export default function CompactListTemplate({ products, currency }: { products: ProductPublic[]; currency: string }) {
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
      <ProductImage product={product} className={styles.thumb} />
      <VegDot foodType={product.food_type} />
      <span className={styles.name}>{product.name}</span>
      <span className={styles.price}>{priceLabel(product, currency)}</span>
    </div>
  )
}
