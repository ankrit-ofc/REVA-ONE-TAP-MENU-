import type { ProductPublic } from '@/lib/schemas/menu'
import { OpenButton, ProductImage, VegDot, priceLabel, useProductOpen } from './shared'
import styles from './MagazineTemplate.module.css'

/** Hero image for the first item in each category, remaining items as a list.
 *  Called once per rendered group, so "first item" = first item of that group. */
export default function MagazineTemplate({ products, currency }: { products: ProductPublic[]; currency: string }) {
  const [hero, ...rest] = products
  if (!hero) return null
  return (
    <div className={styles.wrap}>
      <Hero product={hero} currency={currency} />
      {rest.length > 0 && (
        <div className={styles.list}>
          {rest.map((p) => <Row key={p.id} product={p} currency={currency} />)}
        </div>
      )}
    </div>
  )
}

function Hero({ product, currency }: { product: ProductPublic; currency: string }) {
  const tap = useProductOpen(product)
  return (
    <div className={styles.hero} {...tap} aria-label={`${product.name}, ${priceLabel(product, currency)}`}>
      <ProductImage product={product} className={styles.heroImage} />
      <div className={styles.heroBody}>
        <div className={styles.nameRow}>
          <VegDot foodType={product.food_type} />
          <span className={styles.heroName}>{product.name}</span>
        </div>
        {product.description && <p className={styles.heroDescription}>{product.description}</p>}
        <div className={styles.heroFooter}>
          <span className={styles.heroPrice}>{priceLabel(product, currency)}</span>
          <span className={styles.heroCta}>View <OpenButton /></span>
        </div>
      </div>
    </div>
  )
}

function Row({ product, currency }: { product: ProductPublic; currency: string }) {
  const tap = useProductOpen(product)
  return (
    <div className={styles.row} {...tap} aria-label={`${product.name}, ${priceLabel(product, currency)}`}>
      <ProductImage product={product} className={styles.rowThumb} />
      <div className={styles.rowBody}>
        <div className={styles.nameRow}>
          <VegDot foodType={product.food_type} />
          <span className={styles.rowName}>{product.name}</span>
        </div>
        {product.description && <p className={styles.rowDescription}>{product.description}</p>}
      </div>
      <span className={styles.rowPrice}>{priceLabel(product, currency)}</span>
    </div>
  )
}
