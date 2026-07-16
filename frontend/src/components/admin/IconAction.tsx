import styles from './IconAction.module.css'

export type IconKind = 'view' | 'edit' | 'delete'

interface IconActionProps {
  kind: IconKind
  onClick: () => void
  title: string
  disabled?: boolean
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function PenIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  )
}

const ICON = { view: EyeIcon, edit: PenIcon, delete: TrashIcon }
const TONE = { view: styles.view, edit: styles.edit, delete: styles.delete }

/** Small classic icon action — green eye / blue pen / red trash. Shared by the
 *  desktop tables and the mobile list cards so both look identical. */
export default function IconAction({ kind, onClick, title, disabled }: IconActionProps) {
  const Icon = ICON[kind]
  return (
    <button
      type="button"
      className={`${styles.iconBtn} ${TONE[kind]}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={title}
      title={title}
    >
      <Icon />
    </button>
  )
}
