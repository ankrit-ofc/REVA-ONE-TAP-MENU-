import { useMemo, useState } from 'react'

export const PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100] as const

interface Options<T> {
  /** Returns the searchable text for an item (matched case-insensitively). */
  searchText: (item: T) => string
  initialPageSize?: number
}

export interface PaginatedList<T> {
  search: string
  setSearch: (s: string) => void
  pageSize: number
  setPageSize: (n: number) => void
  page: number
  setPage: (n: number) => void
  total: number
  pageCount: number
  pageItems: T[]
  rangeStart: number
  rangeEnd: number
}

/**
 * Client-side search + pagination over an in-memory array. Filtering and slicing
 * happen in the browser; the source list (and any other consumers of it) are
 * untouched. Changing the search text or page size resets back to page 1.
 */
export function usePaginatedList<T>(items: T[], opts: Options<T>): PaginatedList<T> {
  const { searchText, initialPageSize = 10 } = opts
  const [search, setSearchRaw] = useState('')
  const [pageSize, setPageSizeRaw] = useState(initialPageSize)
  const [page, setPage] = useState(1)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return items
    return items.filter((it) => searchText(it).toLowerCase().includes(q))
    // searchText is treated as stable; callers pass an inline fn but its output
    // only depends on the item, so re-running on every render is acceptable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, search])

  const total = filtered.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const clampedPage = Math.min(page, pageCount)
  const start = (clampedPage - 1) * pageSize
  const pageItems = filtered.slice(start, start + pageSize)

  return {
    search,
    setSearch: (s: string) => { setSearchRaw(s); setPage(1) },
    pageSize,
    setPageSize: (n: number) => { setPageSizeRaw(n); setPage(1) },
    page: clampedPage,
    setPage,
    total,
    pageCount,
    pageItems,
    rangeStart: total === 0 ? 0 : start + 1,
    rangeEnd: Math.min(start + pageSize, total),
  }
}
