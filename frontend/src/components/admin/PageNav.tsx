import type { PaginatedList } from './usePaginatedList'
import styles from './PageNav.module.css'

/** Bottom page navigation: ‹ Page X of Y › — hidden when there's a single page. */
export default function PageNav<T>({ list }: { list: PaginatedList<T> }) {
  const { page, pageCount, setPage } = list

  if (pageCount <= 1) return null

  return (
    <div className={styles.nav}>
      <button
        type="button"
        className={styles.btn}
        onClick={() => setPage(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        ‹
      </button>
      <span className={styles.info}>Page {page} of {pageCount}</span>
      <button
        type="button"
        className={styles.btn}
        onClick={() => setPage(page + 1)}
        disabled={page >= pageCount}
        aria-label="Next page"
      >
        ›
      </button>
    </div>
  )
}
