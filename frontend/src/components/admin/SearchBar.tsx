import styles from './SearchBar.module.css'

interface SearchBarProps {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}

/** Compact search input with a leading 🔍 and a clear button. */
export default function SearchBar({ value, onChange, placeholder = 'Search…' }: SearchBarProps) {
  return (
    <div className={styles.wrap}>
      <span className={styles.icon} aria-hidden="true">🔍</span>
      <input
        type="text"
        className={styles.input}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Search"
      />
      {value && (
        <button type="button" className={styles.clear} onClick={() => onChange('')} aria-label="Clear search">
          ×
        </button>
      )}
    </div>
  )
}
