/**
 * Landing page when an online-gateway (eSewa/Khalti) payment fails or is cancelled.
 *
 * On failure the order is NOT closed and the table session is still valid, so the
 * guest can return to their bill and try again (or pay at the counter). We do NOT
 * end the session here.
 */
import { useNavigate } from 'react-router-dom'
import Button from '@/components/common/Button'
import styles from './BillRequest.module.css'

export default function PaymentFailure() {
  const navigate = useNavigate()

  return (
    <div className={styles.page}>
      <div className={styles.thankYou}>
        <span className={styles.thankIcon} aria-hidden>!</span>
        <h1 className={styles.thankTitle}>Payment didn’t go through</h1>
        <p className={styles.thankNote}>
          Your payment was not completed. You can return to your bill and try again, or pay with
          cash / card at the counter.
        </p>
        <Button onClick={() => navigate('/bill')} style={{ marginTop: '1rem' }}>
          Back to Bill
        </Button>
      </div>
    </div>
  )
}
