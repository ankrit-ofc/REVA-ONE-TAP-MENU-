import { useState } from 'react'
import {
  useListStaffQuery,
  useCreateStaffMutation,
  useUpdateStaffMutation,
  useDeleteStaffMutation,
  type StaffCreate,
} from '@/features/admin/adminApi'
import type { StaffResponse } from '@/lib/schemas/admin'
import EntityCard from '@/components/admin/EntityCard'
import IconAction from '@/components/admin/IconAction'
import ViewModal from '@/components/admin/ViewModal'
import SearchBar from '@/components/admin/SearchBar'
import HeaderControls from '@/components/admin/HeaderControls'
import PageNav from '@/components/admin/PageNav'
import { usePaginatedList } from '@/components/admin/usePaginatedList'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './AdminTable.module.css'

type StaffRole = 'ADMIN' | 'KITCHEN' | 'WAITER' | 'COUNTER' | 'COUNTER_DISPLAY'
const ROLES: StaffRole[] = ['ADMIN', 'KITCHEN', 'WAITER', 'COUNTER', 'COUNTER_DISPLAY']

const ROLE_LABEL: Record<string, string> = {
  ADMIN: 'Admin',
  KITCHEN: 'Kitchen',
  WAITER: 'Waiter',
  COUNTER: 'Counter',
  COUNTER_DISPLAY: 'Counter Display',
  SUPERADMIN: 'Superadmin',
}

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

interface EditRowProps {
  member: StaffResponse
  onClose: () => void
}

function EditRow({ member, onClose }: EditRowProps) {
  const [role, setRole] = useState<StaffRole>(member.role as StaffRole)
  const [updateStaff, { isLoading }] = useUpdateStaffMutation()
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    setError(null)
    try {
      await updateStaff({ id: member.id, role }).unwrap()
      onClose()
    } catch (e) {
      setError(errDetail(e))
    }
  }

  return (
    <>
      <select
        className={styles.inlineInput}
        value={role}
        onChange={(e) => setRole(e.target.value as StaffRole)}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>{ROLE_LABEL[r]}</option>
        ))}
      </select>
      {error && <span className={styles.inlineError}>{error}</span>}
      <button className={styles.btnSave} onClick={() => void handleSave()} disabled={isLoading}>
        {isLoading ? '…' : 'Save'}
      </button>
      <button className={styles.btnCancel} onClick={onClose}>Cancel</button>
    </>
  )
}

function CreateStaffModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<StaffRole>('KITCHEN')
  const [createStaff, { isLoading }] = useCreateStaffMutation()
  const [error, setError] = useState<string | null>(null)
  useOnEscape(onClose)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!email.trim() || password.length < 8) {
      setError('Email required; password must be at least 8 characters.')
      return
    }
    try {
      await createStaff({ email: email.trim(), password, role } satisfies StaffCreate).unwrap()
      onClose()
    } catch (e) {
      setError(errDetail(e))
    }
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Add staff member</h3>
          <button className={styles.modalClose} type="button" onClick={onClose}>×</button>
        </div>
        <form className={styles.modalForm} onSubmit={(e) => void handleCreate(e)}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="staff-email">Email</label>
            <input
              id="staff-email"
              className={styles.input}
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={255}
              autoFocus
            />
          </div>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="staff-pass">Password</label>
            <input
              id="staff-pass"
              className={styles.input}
              type="password"
              placeholder="Min 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              maxLength={100}
              required
            />
          </div>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="staff-role">Role</label>
            <select
              id="staff-role"
              className={styles.input}
              value={role}
              onChange={(e) => setRole(e.target.value as StaffRole)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
          </div>
          {error && <p className={styles.formError}>{error}</p>}
          <div className={styles.modalActions}>
            <button type="button" className={styles.btnCancel} onClick={onClose}>Cancel</button>
            <button type="submit" className={styles.btnAdd} disabled={isLoading}>
              {isLoading ? 'Creating…' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function AdminStaff() {
  const { data: staff, isLoading, isError } = useListStaffQuery()
  const [deleteStaff] = useDeleteStaffMutation()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [viewing, setViewing] = useState<StaffResponse | null>(null)

  const handleDelete = (m: StaffResponse) => {
    const isAdmin = m.role === 'ADMIN'
    const msg = isAdmin
      ? `Deactivate admin ${m.email}? They will no longer be able to sign in.`
      : `Permanently delete ${m.email}? This cannot be undone (their email becomes reusable).`
    if (window.confirm(msg)) void deleteStaff(m.id)
  }

  const list = staff ?? []
  const paged = usePaginatedList(list, { searchText: (m) => m.email })

  if (isLoading) return <div className={styles.page}><p>Loading…</p></div>
  if (isError) return <div className={styles.page}><p className={styles.formError}>Failed to load staff.</p></div>

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Staff</h1>
        <div className={styles.headerRight}>
          <HeaderControls list={paged} placeholder="Search staff…" />
          <button className={styles.btnAddTop} onClick={() => setShowCreate(true)}>
            + Add Staff
          </button>
        </div>
      </div>

      {showCreate && <CreateStaffModal onClose={() => setShowCreate(false)} />}

      {viewing && (
        <ViewModal
          title={viewing.email}
          onClose={() => setViewing(null)}
          rows={[
            { label: 'Email', value: viewing.email },
            { label: 'Role', value: ROLE_LABEL[viewing.role] ?? viewing.role },
            { label: 'Active', value: viewing.is_active ? 'Yes' : 'No' },
          ]}
        />
      )}

      <SearchBar value={paged.search} onChange={paged.setSearch} placeholder="Search staff by email…" />

      {/* Mobile cards */}
      <div className={styles.cardGrid}>
        {paged.pageItems.map((m: StaffResponse) => (
          <EntityCard
            key={m.id}
            showImage={false}
            title={m.email}
            subtitle={ROLE_LABEL[m.role] ?? m.role}
            status={{ label: m.is_active ? 'Active' : 'Inactive', tone: m.is_active ? 'ok' : 'muted' }}
            onView={() => setViewing(m)}
            onEdit={m.is_active ? () => setEditingId(m.id) : undefined}
            onDelete={m.is_active ? () => handleDelete(m) : undefined}
          >
            {editingId === m.id && (
              <div className={styles.cardEdit}>
                <EditRow member={m} onClose={() => setEditingId(null)} />
              </div>
            )}
          </EntityCard>
        ))}
        {paged.total === 0 && (
          <p className={styles.empty}>{list.length === 0 ? 'No staff members yet.' : 'No matches.'}</p>
        )}
      </div>

      <div className={styles.desktopOnly}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {paged.pageItems.map((m: StaffResponse) => (
            <tr key={m.id}>
              <td>{m.email}</td>
              <td>
                {editingId === m.id ? (
                  <EditRow member={m} onClose={() => setEditingId(null)} />
                ) : (
                  ROLE_LABEL[m.role] ?? m.role
                )}
              </td>
              <td>
                <span className={m.is_active ? styles.badgeActive : styles.badgeInactive}>
                  {m.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className={styles.actions}>
                {editingId !== m.id && (
                  <>
                    <IconAction kind="view" onClick={() => setViewing(m)} title="View" />
                    <IconAction kind="edit" onClick={() => setEditingId(m.id)} title="Edit" disabled={!m.is_active} />
                    {m.is_active && (
                      <IconAction kind="delete" onClick={() => handleDelete(m)} title="Delete" />
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
          {paged.total === 0 && (
            <tr>
              <td colSpan={4} className={styles.empty}>{list.length === 0 ? 'No staff members yet.' : 'No matches.'}</td>
            </tr>
          )}
        </tbody>
      </table>
      </div>

      <PageNav list={paged} />
    </div>
  )
}
