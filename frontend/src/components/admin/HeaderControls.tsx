import { useRef, useState } from 'react'
import { PAGE_SIZE_OPTIONS, type PaginatedList } from './usePaginatedList'
import styles from './HeaderControls.module.css'

interface Props<T> {
  list: PaginatedList<T>
  placeholder?: string
}

/**
 * Header-right cluster placed just left of a page's "Add" button:
 *  - a search affordance that on desktop is a 🔍 icon expanding left into an
 *    input (hidden on mobile, where the full SearchBar shows below the header),
 *  - the page-size selector (shown on both).
 */
export default function HeaderControls<T>({ list, placeholder }: Props<T>) {
  const { search, setSearch, pageSize, setPageSize } = list
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const expanded = open || search.length > 0

  return (
    <div className={styles.wrap}>
      <div className={`${styles.searchBox} ${expanded ? styles.searchOpen : ''}`}>
        {expanded && (
          <input
            ref={inputRef}
            className={styles.input}
            value={search}
            placeholder={placeholder ?? 'Search…'}
            onChange={(e) => setSearch(e.target.value)}
            onBlur={() => { if (!search) setOpen(false) }}
            autoFocus
          />
        )}
        <button
          type="button"
          className={styles.iconBtn}
          aria-label="Search"
          onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 0) }}
        >
          🔍
        </button>
      </div>

      <select
        className={styles.select}
        value={pageSize}
        onChange={(e) => setPageSize(Number(e.target.value))}
        aria-label="Rows per page"
      >
        {PAGE_SIZE_OPTIONS.map((n) => (
          <option key={n} value={n}>{n}</option>
        ))}
      </select>
    </div>
  )
}
