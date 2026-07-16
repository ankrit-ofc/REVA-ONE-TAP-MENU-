import { formatPrice } from '@/lib/currency'
import styles from './PriceSummary.module.css'

interface EstimateProps {
  mode: 'estimate'
  currency: string
  subtotal: number
  tax: number
}

interface ServerProps {
  mode: 'server'
  currency: string
  subtotal: number
  discount: number
  taxTotal: number
  total: number
}

type Props = EstimateProps | ServerProps

export default function PriceSummary(props: Props) {
  if (props.mode === 'estimate') {
    const { currency, subtotal, tax } = props
    const total = subtotal + tax

    return (
      <div className={styles.summary}>
        <div className={styles.row}>
          <span className={styles.label}>Subtotal</span>
          <span>{formatPrice(subtotal, currency)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>Tax (est.)</span>
          <span>{formatPrice(tax, currency)}</span>
        </div>
        <div className={styles.totalRow}>
          <span>Total</span>
          <span>{formatPrice(total, currency)}</span>
        </div>
        <p className={styles.estimateNote}>
          * Estimated — final total confirmed at billing.
        </p>
      </div>
    )
  }

  const { currency, subtotal, discount, taxTotal, total } = props

  return (
    <div className={styles.summary}>
      <div className={styles.row}>
        <span className={styles.label}>Subtotal</span>
        <span>{formatPrice(subtotal, currency)}</span>
      </div>
      {discount > 0 && (
        <div className={styles.row}>
          <span className={styles.label}>Discount</span>
          <span>− {formatPrice(discount, currency)}</span>
        </div>
      )}
      <div className={styles.row}>
        <span className={styles.label}>Tax</span>
        <span>{formatPrice(taxTotal, currency)}</span>
      </div>
      <div className={styles.totalRow}>
        <span>Total</span>
        <span>{formatPrice(total, currency)}</span>
      </div>
      <p className={styles.authoritative}>✓ Confirmed server total</p>
    </div>
  )
}
