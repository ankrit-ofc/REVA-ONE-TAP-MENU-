import type { ReactNode } from 'react'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './ViewModal.module.css'

export interface ViewRow {
  label: string
  value: ReactNode
}

interface ViewModalProps {
  title: string
  rows: ViewRow[]
  onClose: () => void
}

/**
 * Read-only "view all data" modal. Each page supplies friendly label/value rows
 * (it deliberately omits internal ids, timestamps and raw UUID foreign keys).
 */
export default function ViewModal({ title, rows, onClose }: ViewModalProps) {
  useOnEscape(onClose)
  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h3 className={styles.title}>{title}</h3>
          <button className={styles.close} type="button" onClick={onClose} aria-label="Close">×</button>
        </div>
        <dl className={styles.list}>
          {rows.map((r) => (
            <div className={styles.row} key={r.label}>
              <dt className={styles.label}>{r.label}</dt>
              <dd className={styles.value}>{r.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
