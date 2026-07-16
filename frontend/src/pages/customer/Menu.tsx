import { useState } from 'react'
import { useMenu } from '@/features/menu/useMenu'
import { useSession } from '@/features/session/useSession'
import { useTheme } from '@/features/ui/useTheme'
import ProductCard from '@/components/ui/ProductCard'
import Loader from '@/components/common/Loader'
import type { CategoryPublic, FoodTypePublic, ProductPublic } from '@/lib/schemas/menu'
import styles from './Menu.module.css'

const CURRENCY = 'NPR'

type Filter = 'ALL' | FoodTypePublic
const FILTER_LABEL: Record<Filter, string> = {
  ALL: 'All', VEG: 'Veg', NON_VEG: 'Non-veg', EGG: 'Egg', BEVERAGE: 'Beverage', SMOKE: 'Smoke',
}

// ── Tree helpers (pure) ─────────────────────────────────────────────────────────

/** All products in a category's whole subtree (its own + every descendant's). */
function subtreeProducts(cat: CategoryPublic): ProductPublic[] {
  const out = [...cat.products]
  for (const child of cat.children) out.push(...subtreeProducts(child))
  return out
}

function countProducts(cat: CategoryPublic): number {
  let n = cat.products.length
  for (const child of cat.children) n += countProducts(child)
  return n
}

/** Resolve a path of ids to the chain of nodes it points at (stops at a broken link). */
function resolvePath(roots: CategoryPublic[], path: string[]): CategoryPublic[] {
  const chain: CategoryPublic[] = []
  let level = roots
  for (const id of path) {
    const node = level.find((c) => c.id === id)
    if (!node) break
    chain.push(node)
    level = node.children
  }
  return chain
}

interface Group { name: string; products: ProductPublic[] }

export default function Menu() {
  const { categories, specials, bannerImageUrl, isLoading, isError } = useMenu()
  const { restaurantName } = useSession()
  const { theme, toggle } = useTheme()
  const [path, setPath] = useState<string[]>([])
  const [filter, setFilter] = useState<Filter>('ALL')
  const [query, setQuery] = useState('')

  if (isLoading) return <Loader fullscreen message="Loading menu…" />

  if (isError) {
    return (
      <div className={styles.errorState}>
        <p>Unable to load the menu. Please try refreshing.</p>
      </div>
    )
  }

  if (categories.length === 0) {
    return (
      <div className={styles.emptyState}>
        <span className={styles.emptyIcon}>🍽️</span>
        <p>No items available right now.</p>
      </div>
    )
  }

  const roots = categories
  const trimmed = query.trim().toLowerCase()
  const isSearching = trimmed.length > 0

  // Resolve the selection into a chain of nodes; the deepest is the "context".
  const chain = resolvePath(roots, path)
  const contextNode = chain.length > 0 ? chain[chain.length - 1] : null

  // Cascading chip rows: row 0 = roots; each selected node with children adds a row.
  const rows: { level: number; options: CategoryPublic[]; selectedId: string | null }[] = [
    { level: 0, options: roots, selectedId: chain[0]?.id ?? null },
  ]
  for (let i = 0; i < chain.length; i++) {
    const kids = chain[i].children.filter((c) => countProducts(c) > 0)
    if (kids.length === 0) break // leaf → no deeper row
    rows.push({ level: i + 1, options: kids, selectedId: chain[i + 1]?.id ?? null })
  }

  const selectAt = (level: number, id: string | null) => {
    setFilter('ALL')
    setQuery('')
    setPath((prev) => {
      const base = prev.slice(0, level)
      if (id == null || prev[level] === id) return base // "All", or toggle selected → collapse
      return [...base, id]
    })
  }

  // Body: products of the deepest selected node's subtree, grouped by immediate
  // subcategory (or by root when nothing is selected). Leaf/one-group → flat list.
  const rawGroups: Group[] = []
  if (contextNode == null) {
    for (const r of roots) rawGroups.push({ name: r.name, products: subtreeProducts(r) })
  } else {
    if (contextNode.products.length > 0) rawGroups.push({ name: contextNode.name, products: contextNode.products })
    for (const child of contextNode.children) {
      const ps = subtreeProducts(child)
      if (ps.length > 0) rawGroups.push({ name: child.name, products: ps })
    }
  }

  const bodyAll = isSearching
    ? categories.flatMap((c) => subtreeProducts(c)).filter((p, i, arr) => arr.indexOf(p) === i)
    : rawGroups.flatMap((g) => g.products)

  const searchResults = isSearching
    ? bodyAll.filter((p) =>
        p.name.toLowerCase().includes(trimmed) ||
        (p.description?.toLowerCase().includes(trimmed) ?? false),
      )
    : []

  const filterBase = isSearching ? searchResults : bodyAll
  const presentTypes = (['VEG', 'NON_VEG', 'EGG', 'BEVERAGE', 'SMOKE'] as FoodTypePublic[]).filter((t) =>
    filterBase.some((p) => p.food_type === t),
  )
  const filters: Filter[] = ['ALL', ...presentTypes]
  const applyVeg = (ps: ProductPublic[]) => (filter === 'ALL' ? ps : ps.filter((p) => p.food_type === filter))

  const vegGroups = rawGroups
    .map((g) => ({ name: g.name, products: applyVeg(g.products) }))
    .filter((g) => g.products.length > 0)

  const breadcrumb = chain.map((n) => n.name).join(' › ')
  const bodyCount = applyVeg(bodyAll).length

  const card = (p: ProductPublic, prefix = '') => (
    <ProductCard key={`${prefix}${p.id}`} product={p} currency={CURRENCY} />
  )

  return (
    <div className={styles.page}>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      {/* Admin-uploaded banner when set; the stock image (CSS default) otherwise. */}
      <section
        className={styles.hero}
        style={
          bannerImageUrl
            ? {
                background:
                  `linear-gradient(rgba(15, 42, 33, 0.5), rgba(15, 42, 33, 0.5)), ` +
                  `url(${bannerImageUrl}) center / cover no-repeat`,
              }
            : undefined
        }
      >
        <button
          className={styles.themeToggle}
          onClick={toggle}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        >
          {theme === 'light' ? (
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
              strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
              strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
            </svg>
          )}
        </button>

        <h1 className={styles.restaurantName}>{restaurantName ?? 'Our Menu'}</h1>
        <p className={styles.tagline}>Good Food, Great Moments</p>
      </section>

      {/* ── Today's Special (hidden entirely when none are flagged) ───────── */}
      {specials.length > 0 && (
        <section className={styles.specials} aria-label="Today's Special">
          <h2 className={styles.specialsTitle}>
            <span aria-hidden="true">⭐</span> Today&rsquo;s Special
          </h2>
          <div className={styles.specialsList}>
            {specials.map((p) => (
              <div key={`special-${p.id}`} className={styles.specialCard}>
                <ProductCard product={p} currency={CURRENCY} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Sticky band: cascading category rows + search + dietary filter ── */}
      <div className={styles.stickyBand}>
        {!isSearching && rows.map((row) => (
          <div
            key={row.level}
            className={`${styles.chipRow} ${row.level === 0 ? styles.chipRow0 : ''}`}
            aria-label={row.level === 0 ? 'Categories' : 'Subcategories'}
          >
            <button
              className={`${styles.chip} ${row.selectedId == null ? styles.chipActive : ''}`}
              onClick={() => selectAt(row.level, null)}
              aria-pressed={row.selectedId == null}
            >
              All
            </button>
            {row.options
              .filter((c) => countProducts(c) > 0)
              .map((c) => (
                <button
                  key={c.id}
                  className={`${styles.chip} ${row.selectedId === c.id ? styles.chipActive : ''}`}
                  onClick={() => selectAt(row.level, c.id)}
                  aria-pressed={row.selectedId === c.id}
                >
                  {c.name}
                  <span className={styles.chipCount}>{countProducts(c)}</span>
                </button>
              ))}
          </div>
        ))}

        <div className={styles.searchWrap}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
            strokeWidth={2} strokeLinecap="round" className={styles.searchIcon} aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3-3" />
          </svg>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search for dishes…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search for dishes"
          />
        </div>

        {!isSearching && (breadcrumb || filters.length > 1) && (
          <div className={styles.selectionBar} role="group" aria-label="Selection and dietary filter">
            {breadcrumb && (
              <span className={styles.breadcrumb}>{breadcrumb} · {bodyCount} item{bodyCount !== 1 ? 's' : ''}</span>
            )}
            {filters.length > 1 && filters.map((f) => (
              <button
                key={f}
                className={`${styles.filterBtn} ${filter === f ? styles.filterActive : ''}`}
                onClick={() => setFilter(f)}
                aria-pressed={filter === f}
              >
                {FILTER_LABEL[f]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Product area ─────────────────────────────────────────────────── */}
      <div className={styles.menuArea}>
        {isSearching ? (
          applyVeg(searchResults).length > 0 ? (
            <div className={styles.list}>{applyVeg(searchResults).map((p) => card(p))}</div>
          ) : (
            <p className={styles.emptyCategory}>No dishes match “{query.trim()}”.</p>
          )
        ) : vegGroups.length === 0 ? (
          <p className={styles.emptyCategory}>
            No {filter !== 'ALL' ? `${FILTER_LABEL[filter].toLowerCase()} ` : ''}items here.
          </p>
        ) : vegGroups.length === 1 ? (
          // Leaf / single group → flat list, no header.
          <div className={styles.list}>{vegGroups[0].products.map((p) => card(p, `${vegGroups[0].name}-`))}</div>
        ) : (
          vegGroups.map((g) => (
            <section key={g.name} className={styles.group} aria-label={g.name}>
              <h2 className={styles.listTitle}>{g.name}</h2>
              <div className={styles.list}>{g.products.map((p) => card(p, `${g.name}-`))}</div>
            </section>
          ))
        )}
      </div>
    </div>
  )
}
