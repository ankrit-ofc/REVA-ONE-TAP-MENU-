/**
 * Stacked, auto-dismissing toast notifications for the staff dashboard.
 * Fed by useStaffAlerts (e.g. a customer calling a waiter) and rendered once in
 * StaffLayout. Visible regardless of the sound-alerts toggle.
 */
import type { StaffToast } from '@/lib/useStaffAlerts'
import styles from './StaffToasts.module.css'

interface Props {
  toasts: StaffToast[]
  onDismiss: (id: string) => void
}

export default function StaffToasts({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null

  return (
    <div className={styles.wrap}>
      {toasts.map((t) => (
        <div key={t.id} className={styles.toast} role="status">
          <span className={styles.icon} aria-hidden>🔔</span>
          <span className={styles.text}>{t.text}</span>
          <button
            className={styles.close}
            onClick={() => onDismiss(t.id)}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
