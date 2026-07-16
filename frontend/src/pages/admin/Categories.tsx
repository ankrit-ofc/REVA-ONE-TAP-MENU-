import { useState } from 'react'
import {
  useListCategoriesQuery,
  useCreateCategoryMutation,
  useUpdateCategoryMutation,
  useSoftDeleteCategoryMutation,
} from '@/features/admin/adminApi'
import type { CategoryResponse } from '@/lib/schemas/admin'
import { indentedCategoryOptions, descendantIdsWithSelf } from '@/features/menu/categoryTree'
import EntityCard from '@/components/admin/EntityCard'
import IconAction from '@/components/admin/IconAction'
import ViewModal from '@/components/admin/ViewModal'
import SearchBar from '@/components/admin/SearchBar'
import HeaderControls from '@/components/admin/HeaderControls'
import PageNav from '@/components/admin/PageNav'
import { usePaginatedList } from '@/components/admin/usePaginatedList'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './AdminTable.module.css'

const yesNo = (b: boolean) => (b ? 'Yes' : 'No')

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

// Fixed set of display priorities. Lower value = shown first in the customer
// menu (get_customer_menu orders by display_order ascending). 10 options, 0–9.
const PRIORITY_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: 'First Priority' },
  { value: 1, label: 'Second Priority' },
  { value: 2, label: 'Third Priority' },
  { value: 3, label: 'Fourth Priority' },
  { value: 4, label: 'Fifth Priority' },
  { value: 5, label: 'Sixth Priority' },
  { value: 6, label: 'Seventh Priority' },
  { value: 7, label: 'Eighth Priority' },
  { value: 8, label: 'Ninth Priority' },
  { value: 9, label: 'Tenth Priority' },
]

function priorityLabel(n: number): string {
  return PRIORITY_OPTIONS.find((o) => o.value === n)?.label ?? `Priority ${n + 1}`
}

// ── Add / Edit modal ──────────────────────────────────────────────────────────

interface CategoryModalProps {
  /** When provided, the modal edits this category; otherwise it creates one. */
  category?: CategoryResponse
  /** All active categories, for the parent picker. */
  categories: CategoryResponse[]
  onClose: () => void
}

function CategoryModal({ category, categories, onClose }: CategoryModalProps) {
  const isEdit = category != null
  const [name, setName] = useState(category?.name ?? '')
  const [order, setOrder] = useState<number>(category?.display_order ?? 0)
  const [isAvailable, setIsAvailable] = useState(category?.is_available ?? true)
  const [isSub, setIsSub] = useState<boolean>(category?.parent_id != null)
  const [parentId, setParentId] = useState<string>(category?.parent_id ?? '')
  const [error, setError] = useState<string | null>(null)

  const [createCategory, { isLoading: isCreating }] = useCreateCategoryMutation()
  const [updateCategory, { isLoading: isUpdating }] = useUpdateCategoryMutation()
  const isSaving = isCreating || isUpdating
  useOnEscape(onClose)

  // Show the current value even if a legacy category sits outside the 0–9 set.
  const hasFallbackOption = !PRIORITY_OPTIONS.some((o) => o.value === order)

  // Parent options: any active category except this one and its descendants
  // (a category can't be nested under its own subtree — mirrors the backend guard).
  const excluded = isEdit ? descendantIdsWithSelf(categories, category.id) : new Set<string>()
  const parentOptions = indentedCategoryOptions(categories).filter(({ cat }) => !excluded.has(cat.id))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) { setError('Name is required.'); return }
    if (isSub && !parentId) { setError('Pick a parent category, or uncheck sub-category.'); return }
    const display_order = order
    const parent = isSub ? parentId : null
    try {
      if (isEdit) {
        await updateCategory({
          id: category.id,
          name: name.trim(),
          display_order,
          is_available: isAvailable,
          parent_id: parent,
          parent_id_set: true,
        }).unwrap()
      } else {
        await createCategory({
          name: name.trim(),
          display_order,
          is_available: isAvailable,
          parent_id: parent,
        }).unwrap()
      }
      onClose()
    } catch (err) {
      setError(errDetail(err))
    }
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>{isEdit ? 'Edit Category' : 'Add Category'}</h3>
          <button className={styles.modalClose} onClick={onClose} type="button">×</button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className={styles.modalForm}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="cat-name">Category Name</label>
            <input
              id="cat-name"
              className={styles.input}
              placeholder="e.g. Appetizers"
              value={name}
              onChange={(e) => setName(e.target.value.slice(0, 80))}
              maxLength={80}
              autoFocus
            />
          </div>

          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={isSub}
              onChange={(e) => setIsSub(e.target.checked)}
            />
            This is a sub-category
          </label>

          {isSub && (
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="cat-parent">Parent category</label>
              <select
                id="cat-parent"
                className={styles.input}
                value={parentId}
                onChange={(e) => setParentId(e.target.value)}
              >
                <option value="">Select a parent…</option>
                {parentOptions.map(({ cat, depth }) => (
                  <option key={cat.id} value={cat.id}>
                    {`${'  '.repeat(depth)}${depth > 0 ? '└ ' : ''}${cat.name}`}
                  </option>
                ))}
              </select>
              <span className={styles.fieldHint}>This category will appear nested under the parent.</span>
            </div>
          )}

          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="cat-order">Category Display Priority in Menu</label>
            <select
              id="cat-order"
              className={styles.input}
              value={order}
              onChange={(e) => setOrder(Number(e.target.value))}
            >
              {hasFallbackOption && <option value={order}>{priorityLabel(order)}</option>}
              {PRIORITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <span className={styles.fieldHint}>Higher priority appears first in the customer menu.</span>
          </div>

          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={isAvailable}
              onChange={(e) => setIsAvailable(e.target.checked)}
            />
            Available in customer menu
          </label>

          {error && <p className={styles.formError}>{error}</p>}

          <div className={styles.modalActions}>
            <button className={styles.btnCancel} type="button" onClick={onClose}>Cancel</button>
            <button className={styles.btnAdd} type="submit" disabled={isSaving || !name.trim()}>
              {isSaving ? 'Saving…' : isEdit ? 'Save' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminCategories() {
  const { data: categories, isLoading, isError } = useListCategoriesQuery()
  const [softDelete] = useSoftDeleteCategoryMutation()

  const [showAdd, setShowAdd] = useState(false)
  const [editing, setEditing] = useState<CategoryResponse | null>(null)
  const [viewing, setViewing] = useState<CategoryResponse | null>(null)

  const list = categories ?? []
  const paged = usePaginatedList(list, { searchText: (c) => c.name })

  if (isLoading) return <div className={styles.state}>Loading categories…</div>
  if (isError) return <div className={styles.state} style={{ color: '#dc2626' }}>Failed to load categories.</div>

  const handleDelete = (cat: CategoryResponse) => {
    const ok = window.confirm(
      `Delete "${cat.name}"?\n\nThis category and all its products will be removed from the menu. ` +
      `This can't be undone from here.`,
    )
    if (ok) void softDelete(cat.id)
  }

  return (
    <div className={styles.page}>
      {showAdd && <CategoryModal categories={list} onClose={() => setShowAdd(false)} />}
      {editing && (
        <CategoryModal category={editing} categories={list} onClose={() => setEditing(null)} />
      )}
      {viewing && (
        <ViewModal
          title={viewing.name}
          onClose={() => setViewing(null)}
          rows={[
            { label: 'Name', value: viewing.name },
            {
              label: 'Parent',
              value: viewing.parent_id
                ? (list.find((c) => c.id === viewing.parent_id)?.name ?? '—')
                : 'Top-level',
            },
            { label: 'Display Priority', value: priorityLabel(viewing.display_order) },
            { label: 'Available', value: yesNo(viewing.is_available) },
            { label: 'Active', value: yesNo(viewing.is_active) },
          ]}
        />
      )}

      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Categories</h1>
        <div className={styles.headerRight}>
          <HeaderControls list={paged} placeholder="Search categories…" />
          <button className={styles.btnAddTop} onClick={() => setShowAdd(true)}>+ Add Category</button>
        </div>
      </div>

      <SearchBar value={paged.search} onChange={paged.setSearch} placeholder="Search categories…" />

      {/* Mobile cards */}
      <div className={styles.cardGrid}>
        {paged.pageItems.map((cat) => (
          <EntityCard
            key={cat.id}
            showImage={false}
            title={cat.name}
            subtitle={priorityLabel(cat.display_order)}
            status={{ label: cat.is_available ? 'Available' : 'Hidden', tone: cat.is_available ? 'ok' : 'warn' }}
            onView={() => setViewing(cat)}
            onEdit={() => setEditing(cat)}
            onDelete={() => handleDelete(cat)}
          />
        ))}
        {paged.total === 0 && (
          <p className={styles.empty}>{list.length === 0 ? 'No categories yet.' : 'No matches.'}</p>
        )}
      </div>

      <div className={`${styles.tableWrap} ${styles.desktopOnly}`}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Display Priority</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {paged.pageItems.map((cat) => (
              <tr key={cat.id}>
                <td>{cat.name}</td>
                <td>{priorityLabel(cat.display_order)}</td>
                <td>
                  <span className={cat.is_available ? styles.badgeAvailable : styles.badgeHidden}>
                    {cat.is_available ? 'Available' : 'Hidden'}
                  </span>
                </td>
                <td className={styles.actions}>
                  <IconAction kind="view" onClick={() => setViewing(cat)} title="View" />
                  <IconAction kind="edit" onClick={() => setEditing(cat)} title="Edit" />
                  <IconAction kind="delete" onClick={() => handleDelete(cat)} title="Delete" />
                </td>
              </tr>
            ))}
            {paged.total === 0 && (
              <tr><td colSpan={4} className={styles.emptyRow}>{list.length === 0 ? 'No categories yet.' : 'No matches.'}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <PageNav list={paged} />
    </div>
  )
}
