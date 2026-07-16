/**
 * Terminal screen shown once a table's bill is paid and the session has ended.
 * A dead-end: the only way forward is to physically re-scan the table QR.
 * Reuses the bill page's "thank you" styles.
 */
import { formatPrice } from '@/lib/currency'
import type { SessionEndedInfo } from '@/features/session/qrStorage'
import styles from './BillRequest.module.css'

const CURRENCY = 'NPR'

export default function SessionEndedScreen({ info }: { info?: SessionEndedInfo | null }) {
  return (
    <div className={styles.page}>
      <div className={styles.thankYou}>
        <span className={styles.thankIcon} aria-hidden>✓</span>
        <h1 className={styles.thankTitle}>Payment complete — Thank you!</h1>
        {info?.invoiceNumber && <p className={styles.thankSub}>Invoice {info.invoiceNumber}</p>}
        {typeof info?.total === 'number' && (
          <p className={styles.thankTotal}>{formatPrice(info.total, CURRENCY)}</p>
        )}
        <p className={styles.thankNote}>
          Your table session has ended. Scan the table QR again to start a new order.
        </p>
      </div>
    </div>
  )
}
