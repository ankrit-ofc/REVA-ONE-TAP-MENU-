import { useState } from 'react'
import {
  useListAddonsQuery,
  useCreateAddonMutation,
  useUpdateAddonMutation,
  useSoftDeleteAddonMutation,
} from '@/features/admin/adminApi'
import type { AddonResponse } from '@/lib/schemas/admin'
import EntityCard from '@/components/admin/EntityCard'
import IconAction from '@/components/admin/IconAction'
import ViewModal from '@/components/admin/ViewModal'
import SearchBar from '@/components/admin/SearchBar'
import HeaderControls from '@/components/admin/HeaderControls'
import PageNav from '@/components/admin/PageNav'
import { usePaginatedList } from '@/components/admin/usePaginatedList'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './AdminTable.module.css'

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

// ── Add / Edit modal ──────────────────────────────────────────────────────────

function AddonModal({ addon, onClose }: { addon?: AddonResponse; onClose: () => void }) {
  const isEdit = addon != null
  const [name, setName] = useState(addon?.name ?? '')
  const [price, setPrice] = useState(addon ? String(addon.price) : '')
  const [error, setError] = useState<string | null>(null)
  const [createAddon, { isLoading: creating }] = useCreateAddonMutation()
  const [updateAddon, { isLoading: updating }] = useUpdateAddonMutation()
  const saving = creating || updating
  useOnEscape(onClose)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) { setError('Name is required.'); return }
    const p = parseFloat(price)
    if (isNaN(p) || p < 0) { setError('Enter a valid price.'); return }
    try {
      if (isEdit) await updateAddon({ id: addon.id, name: name.trim(), price: p }).unwrap()
      else await createAddon({ name: name.trim(), price: p }).unwrap()
      onClose()
    } catch (err) { setError(errDetail(err)) }
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>{isEdit ? 'Edit Add-on' : 'Add Add-on'}</h3>
          <button className={styles.modalClose} type="button" onClick={onClose}>×</button>
        </div>
        <form onSubmit={(e) => void submit(e)} className={styles.modalForm}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="ad-name">Name</label>
            <input id="ad-name" className={styles.input} value={name} onChange={(e) => setName(e.target.value.slice(0, 60))} maxLength={60} placeholder="e.g. Extra Cheese" autoFocus />
          </div>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="ad-price">Price (NPR)</label>
            <input id="ad-price" className={styles.input} type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" />
          </div>
          {error && <p className={styles.formError}>{error}</p>}
          <div className={styles.modalActions}>
            <button type="button" className={styles.btnCancel} onClick={onClose}>Cancel</button>
            <button type="submit" className={styles.btnAdd} disabled={saving}>{saving ? 'Saving…' : isEdit ? 'Save' : 'Add'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AdminAddons() {
  const { data: addons, isLoading, isError } = useListAddonsQuery()
  const [softDelete] = useSoftDeleteAddonMutation()
  const [showAdd, setShowAdd] = useState(false)
  const [editing, setEditing] = useState<AddonResponse | null>(null)
  const [viewing, setViewing] = useState<AddonResponse | null>(null)

  const list = (addons ?? []).filter((a) => a.is_active)
  const paged = usePaginatedList(list, { searchText: (a) => a.name })

  if (isLoading) return <div className={styles.state}>Loading add-ons…</div>
  if (isError) return <div className={styles.state} style={{ color: '#dc2626' }}>Failed to load add-ons.</div>

  const handleDelete = (a: AddonResponse) => {
    if (window.confirm(`Delete add-on "${a.name}"?\n\nIt will be removed from any products it's mapped to. Past orders are unaffected.`)) {
      void softDelete(a.id)
    }
  }

  return (
    <div className={styles.page}>
      {showAdd && <AddonModal onClose={() => setShowAdd(false)} />}
      {editing && <AddonModal addon={editing} onClose={() => setEditing(null)} />}
      {viewing && (
        <ViewModal
          title={viewing.name}
          onClose={() => setViewing(null)}
          rows={[
            { label: 'Name', value: viewing.name },
            { label: 'Price', value: `NPR ${viewing.price.toFixed(2)}` },
            { label: 'Active', value: viewing.is_active ? 'Yes' : 'No' },
          ]}
        />
      )}

      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Add-ons</h1>
        <div className={styles.headerRight}>
          <HeaderControls list={paged} placeholder="Search add-ons…" />
          <button className={styles.btnAddTop} onClick={() => setShowAdd(true)}>+ Add Add-on</button>
        </div>
      </div>

      <p className={styles.state} style={{ padding: '0 0 1rem', fontSize: '0.875rem' }}>
        A shared pool of optional paid extras. Map them onto products from the Products page.
      </p>

      <SearchBar value={paged.search} onChange={paged.setSearch} placeholder="Search add-ons…" />

      {/* Mobile cards */}
      <div className={styles.cardGrid}>
        {paged.pageItems.map((a) => (
          <EntityCard
            key={a.id}
            showImage={false}
            title={a.name}
            subtitle={`NPR ${a.price.toFixed(2)}`}
            status={{ label: 'Active', tone: 'ok' }}
            onView={() => setViewing(a)}
            onEdit={() => setEditing(a)}
            onDelete={() => handleDelete(a)}
          />
        ))}
        {paged.total === 0 && (
          <p className={styles.empty}>{list.length === 0 ? 'No add-ons yet.' : 'No matches.'}</p>
        )}
      </div>

      <div className={`${styles.tableWrap} ${styles.desktopOnly}`}>
        <table className={styles.table}>
          <thead>
            <tr><th>Name</th><th>Price</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {paged.pageItems.map((a) => (
              <tr key={a.id}>
                <td>{a.name}</td>
                <td>NPR {a.price.toFixed(2)}</td>
                <td className={styles.actions}>
                  <IconAction kind="view" onClick={() => setViewing(a)} title="View" />
                  <IconAction kind="edit" onClick={() => setEditing(a)} title="Edit" />
                  <IconAction kind="delete" onClick={() => handleDelete(a)} title="Delete" />
                </td>
              </tr>
            ))}
            {paged.total === 0 && (
              <tr><td colSpan={3} className={styles.emptyRow}>{list.length === 0 ? 'No add-ons yet.' : 'No matches.'}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <PageNav list={paged} />
    </div>
  )
}
