import { useState } from 'react'
import {
  useListRestaurantsQuery,
  useCreateRestaurantMutation,
  useUpdateRestaurantMutation,
  useUpdateAdminEmailMutation,
} from '@/features/superadmin/superadminApi'
import type { RestaurantResponse } from '@/lib/schemas/superadmin'
import EntityCard from '@/components/admin/EntityCard'
import IconAction from '@/components/admin/IconAction'
import ViewModal from '@/components/admin/ViewModal'
import SearchBar from '@/components/admin/SearchBar'
import HeaderControls from '@/components/admin/HeaderControls'
import PageNav from '@/components/admin/PageNav'
import { usePaginatedList } from '@/components/admin/usePaginatedList'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './Superadmin.module.css'

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

function adminsText(r: RestaurantResponse): string {
  return r.admins.length === 0 ? 'No admin' : r.admins.map((a) => a.email).join(', ')
}

// ── Create modal ────────────────────────────────────────────────────────────

function CreateRestaurantModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [createRestaurant, { isLoading }] = useCreateRestaurantMutation()
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<{ name: string; slug: string; email: string } | null>(null)
  useOnEscape(onClose)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim() || !slug.trim() || !adminEmail.trim() || adminPassword.length < 8) {
      setError('All fields required; password must be at least 8 characters.')
      return
    }
    if (!/^[a-z0-9-]+$/.test(slug)) {
      setError('Slug must be lowercase alphanumeric with hyphens only (e.g. my-restaurant).')
      return
    }
    try {
      const res = await createRestaurant({
        name: name.trim(),
        slug: slug.trim(),
        admin_email: adminEmail.trim(),
        admin_password: adminPassword,
      }).unwrap()
      setCreated({ name: res.restaurant.name, slug: res.restaurant.slug, email: res.admin_email })
    } catch (e) {
      setError(errDetail(e))
    }
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>{created ? 'Restaurant created' : 'Create new restaurant'}</h3>
          <button className={styles.modalClose} type="button" onClick={onClose}>×</button>
        </div>

        {created ? (
          <>
            <div className={styles.successBanner}>
              Restaurant <strong>{created.name}</strong> (<code>{created.slug}</code>) created.
              Admin login: <strong>{created.email}</strong>
            </div>
            <div className={styles.modalActions}>
              <button className={styles.btnSubmit} onClick={onClose}>Done</button>
            </div>
          </>
        ) : (
          <form className={styles.modalForm} onSubmit={(e) => void handleCreate(e)}>
            <p className={styles.modalWarn}>
              ⚠️ The <strong>Restaurant Identifier</strong> is the permanent login key and
              <strong> can’t be changed</strong> after creation. The name and admin email can be
              edited later.
            </p>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Restaurant name</span>
                <input
                  className={styles.formInput}
                  type="text"
                  placeholder="e.g. Spice Garden"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={255}
                  required
                  autoFocus
                />
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Restaurant Identifier</span>
                <input
                  className={styles.formInput}
                  type="text"
                  placeholder="e.g. spice-garden"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                  maxLength={100}
                  required
                />
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Admin email</span>
                <input
                  className={styles.formInput}
                  type="email"
                  placeholder="admin@example.com"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  maxLength={255}
                  required
                />
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Admin password</span>
                <input
                  className={styles.formInput}
                  type="password"
                  placeholder="Min 8 characters"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  minLength={8}
                  maxLength={100}
                  required
                />
              </label>
            {error && <p className={styles.formError}>{error}</p>}
            <div className={styles.modalActions}>
              <button type="button" className={styles.btnCancel} onClick={onClose}>Cancel</button>
              <button className={styles.btnSubmit} type="submit" disabled={isLoading}>
                {isLoading ? 'Creating…' : 'Create Restaurant'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

// ── Edit modal (name / admin email / activate-deactivate) ────────────────────

function AdminEmailRow({
  restaurantId,
  admin,
}: {
  restaurantId: string
  admin: { id: string; email: string }
}) {
  const [email, setEmail] = useState(admin.email)
  const [updateAdminEmail, { isLoading }] = useUpdateAdminEmailMutation()
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const dirty = email.trim() !== admin.email

  const handleSave = async () => {
    setError(null)
    setSaved(false)
    if (!email.trim()) {
      setError('Email is required.')
      return
    }
    try {
      await updateAdminEmail({ restaurantId, userId: admin.id, email: email.trim() }).unwrap()
      setSaved(true)
    } catch (e) {
      setError(errDetail(e))
    }
  }

  return (
    <div className={styles.field}>
      <span className={styles.fieldLabel}>Admin email</span>
      <div className={styles.inlineRow}>
        <input
          className={styles.formInput}
          type="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setSaved(false) }}
          maxLength={255}
        />
        <button
          className={styles.btnSubmit}
          disabled={isLoading || !dirty}
          onClick={() => void handleSave()}
        >
          {isLoading ? '…' : 'Save'}
        </button>
      </div>
      {error && <span className={styles.formError}>{error}</span>}
      {saved && <span className={styles.savedNote}>Saved ✓</span>}
    </div>
  )
}

function EditRestaurantModal({ restaurant, onClose }: { restaurant: RestaurantResponse; onClose: () => void }) {
  const [updateRestaurant, { isLoading }] = useUpdateRestaurantMutation()
  const [name, setName] = useState(restaurant.name)
  const [nameError, setNameError] = useState<string | null>(null)
  const [nameSaved, setNameSaved] = useState(false)
  useOnEscape(onClose)

  const nameDirty = name.trim() !== restaurant.name

  const saveName = async () => {
    setNameError(null)
    setNameSaved(false)
    if (!name.trim()) {
      setNameError('Name is required.')
      return
    }
    try {
      await updateRestaurant({ id: restaurant.id, name: name.trim() }).unwrap()
      setNameSaved(true)
    } catch (e) {
      setNameError(errDetail(e))
    }
  }

  const setActive = async (active: boolean) => {
    await updateRestaurant({ id: restaurant.id, is_active: active })
    onClose()
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Edit {restaurant.name}</h3>
          <button className={styles.modalClose} type="button" onClick={onClose}>×</button>
        </div>

        {/* Name (editable) */}
        <div className={styles.field}>
          <span className={styles.fieldLabel}>Restaurant name</span>
          <div className={styles.inlineRow}>
            <input
              className={styles.formInput}
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setNameSaved(false) }}
              maxLength={255}
            />
            <button
              className={styles.btnSubmit}
              disabled={isLoading || !nameDirty}
              onClick={() => void saveName()}
            >
              Save
            </button>
          </div>
          {nameError && <span className={styles.formError}>{nameError}</span>}
          {nameSaved && <span className={styles.savedNote}>Saved ✓</span>}
        </div>

        {/* Restaurant Identifier (read-only, permanent) */}
        <div className={styles.field}>
          <span className={styles.fieldLabel}>Restaurant Identifier</span>
          <div className={styles.readonly}>{restaurant.slug}</div>
          <span className={styles.hint}>Permanent login key — can’t be changed.</span>
        </div>

        {/* Admin email(s) */}
        {restaurant.admins.length === 0 ? (
          <div className={styles.field}>
            <span className={styles.fieldLabel}>Admin email</span>
            <span className={styles.noAdmin}>No admin user.</span>
          </div>
        ) : (
          restaurant.admins.map((a) => (
            <AdminEmailRow key={a.id} restaurantId={restaurant.id} admin={a} />
          ))
        )}

        {/* Status */}
        <div className={styles.field}>
          <span className={styles.fieldLabel}>Status</span>
          <div className={styles.statusRow}>
            {restaurant.is_active ? (
              <button className={styles.btnDeactivate} disabled={isLoading} onClick={() => void setActive(false)}>
                Deactivate
              </button>
            ) : (
              <button className={styles.btnSubmit} disabled={isLoading} onClick={() => void setActive(true)}>
                Activate
              </button>
            )}
          </div>
        </div>

        <div className={styles.modalActions}>
          <button type="button" className={styles.btnCancel} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SuperadminRestaurants() {
  const { data: restaurants, isLoading, isError } = useListRestaurantsQuery()
  const [showCreate, setShowCreate] = useState(false)
  const [viewing, setViewing] = useState<RestaurantResponse | null>(null)
  const [editing, setEditing] = useState<RestaurantResponse | null>(null)

  const list = restaurants ?? []
  const paged = usePaginatedList(list, {
    searchText: (r) => `${r.name} ${r.slug} ${adminsText(r)}`,
  })

  if (isLoading) {
    return <div className={styles.root}><p>Loading…</p></div>
  }

  if (isError) {
    return (
      <div className={styles.root}>
        <p className={styles.formError}>Failed to load restaurants.</p>
      </div>
    )
  }

  return (
    <div className={styles.root}>
      {showCreate && <CreateRestaurantModal onClose={() => setShowCreate(false)} />}
      {editing && <EditRestaurantModal restaurant={editing} onClose={() => setEditing(null)} />}
      {viewing && (
        <ViewModal
          title={viewing.name}
          onClose={() => setViewing(null)}
          rows={[
            { label: 'Name', value: viewing.name },
            { label: 'Restaurant Identifier', value: viewing.slug },
            { label: 'Admin(s)', value: adminsText(viewing) },
            { label: 'Status', value: viewing.is_active ? 'Active' : 'Inactive' },
            { label: 'Created', value: new Date(viewing.created_at).toLocaleDateString() },
          ]}
        />
      )}

      <div className={styles.pageHeader}>
        <h1 className={styles.title}>Platform Management</h1>
        <div className={styles.headerRight}>
          <HeaderControls list={paged} placeholder="Search restaurants…" />
          <button className={styles.btnAddTop} onClick={() => setShowCreate(true)}>+ New Restaurant</button>
        </div>
      </div>

      <SearchBar value={paged.search} onChange={paged.setSearch} placeholder="Search restaurants…" />

      {/* Mobile cards */}
      <div className={styles.cardGrid}>
        {paged.pageItems.map((r) => (
          <EntityCard
            key={r.id}
            showImage={false}
            title={r.name}
            subtitle={r.slug}
            status={{ label: r.is_active ? 'Active' : 'Inactive', tone: r.is_active ? 'ok' : 'muted' }}
            onView={() => setViewing(r)}
            onEdit={() => setEditing(r)}
          />
        ))}
        {paged.total === 0 && (
          <p className={styles.empty}>{list.length === 0 ? 'No restaurants yet.' : 'No matches.'}</p>
        )}
      </div>

      <div className={`${styles.tableWrap} ${styles.desktopOnly}`}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Identifier</th>
              <th>Admin(s)</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {paged.pageItems.map((r: RestaurantResponse) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td><span className={styles.slugChip}>{r.slug}</span></td>
                <td>
                  {r.admins.length === 0 ? (
                    <span className={styles.noAdmin}>No admin</span>
                  ) : (
                    <div className={styles.adminList}>
                      {r.admins.map((a) => (
                        <span key={a.email} className={styles.adminEmail}>{a.email}</span>
                      ))}
                    </div>
                  )}
                </td>
                <td>
                  <span className={r.is_active ? styles.badgeActive : styles.badgeInactive}>
                    {r.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className={styles.actions}>
                  <IconAction kind="view" onClick={() => setViewing(r)} title="View" />
                  <IconAction kind="edit" onClick={() => setEditing(r)} title="Edit" />
                </td>
              </tr>
            ))}
            {paged.total === 0 && (
              <tr>
                <td colSpan={5} className={styles.empty}>{list.length === 0 ? 'No restaurants yet.' : 'No matches.'}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <PageNav list={paged} />
    </div>
  )
}
