import { PAGE_SIZE_OPTIONS, type PaginatedList } from './usePaginatedList'
import styles from './Pagination.module.css'

/** Bottom bar: page-size selector, "showing a–b of N", and prev/next paging.
 *  Hidden entirely when there's nothing to show. */
export default function Pagination<T>({ list }: { list: PaginatedList<T> }) {
  const { total, page, pageCount, pageSize, setPageSize, setPage, rangeStart, rangeEnd } = list

  if (total === 0) return null

  return (
    <div className={styles.bar}>
      <label className={styles.sizeLabel}>
        Rows
        <select
          className={styles.select}
          value={pageSize}
          onChange={(e) => setPageSize(Number(e.target.value))}
        >
          {PAGE_SIZE_OPTIONS.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <span className={styles.range}>
        {rangeStart}–{rangeEnd} of {total}
      </span>

      <div className={styles.pager}>
        <button
          type="button"
          className={styles.navBtn}
          onClick={() => setPage(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          ‹
        </button>
        <span className={styles.pageInfo}>Page {page} of {pageCount}</span>
        <button
          type="button"
          className={styles.navBtn}
          onClick={() => setPage(page + 1)}
          disabled={page >= pageCount}
          aria-label="Next page"
        >
          ›
        </button>
      </div>
    </div>
  )
}
