import type { ReactNode } from 'react'
import IconAction from './IconAction'
import styles from './EntityCard.module.css'

export interface EntityCardStatus {
  label: string
  /** Visual tone of the status pill. */
  tone: 'ok' | 'warn' | 'muted'
}

interface EntityCardProps {
  /** Optional image URL; falls back to a placeholder glyph when absent. */
  image?: string | null
  /** Placeholder glyph shown when there is no image (defaults to 🍱). */
  placeholder?: string
  /** Set to false to render no image slot at all (e.g. staff, tables). */
  showImage?: boolean
  title: string
  subtitle?: ReactNode
  status?: EntityCardStatus
  onView: () => void
  onEdit?: () => void
  onDelete?: () => void
  /** Optional content rendered in the body, below the status (e.g. a QR button). */
  bodyExtra?: ReactNode
  /** Optional content rendered below the row (e.g. an inline editor). */
  children?: ReactNode
}

const TONE_CLASS: Record<EntityCardStatus['tone'], string> = {
  ok: styles.pillOk,
  warn: styles.pillWarn,
  muted: styles.pillMuted,
}

/**
 * Compact list card used on small screens in place of a wide data table.
 * Layout: [image] [title/subtitle/status/extra] [stacked icon actions on the right].
 */
export default function EntityCard({
  image,
  placeholder = '🍱',
  showImage = true,
  title,
  subtitle,
  status,
  onView,
  onEdit,
  onDelete,
  bodyExtra,
  children,
}: EntityCardProps) {
  return (
    <div className={styles.card}>
      <div className={styles.row}>
        {showImage &&
          (image ? (
            <img src={image} alt="" className={styles.image} />
          ) : (
            <div className={styles.placeholder}>{placeholder}</div>
          ))}

        <div className={styles.body}>
          <div className={styles.title} title={title}>{title}</div>
          {subtitle != null && <div className={styles.subtitle}>{subtitle}</div>}
          {status && <span className={`${styles.pill} ${TONE_CLASS[status.tone]}`}>{status.label}</span>}
          {bodyExtra}
        </div>

        <div className={styles.actions}>
          <IconAction kind="view" onClick={onView} title="View" />
          {onEdit && <IconAction kind="edit" onClick={onEdit} title="Edit" />}
          {onDelete && <IconAction kind="delete" onClick={onDelete} title="Delete" />}
        </div>
      </div>

      {children}
    </div>
  )
}
