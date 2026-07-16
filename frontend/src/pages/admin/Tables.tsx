import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import jsPDF from 'jspdf'
import {
  useListTablesQuery,
  useCreateTableMutation,
  useUpdateTableMutation,
  useDeactivateTableMutation,
} from '@/features/admin/adminApi'
import type { TableResponse } from '@/lib/schemas/admin'
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
  if (typeof e === 'object' && e && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

// ── QR Modal ─────────────────────────────────────────────────────────────────

interface QRModalProps {
  table: TableResponse
  onClose: () => void
}

function QRModal({ table, onClose }: QRModalProps) {
  const [dataUrl, setDataUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [exporting, setExporting] = useState(false)
  useOnEscape(onClose)

  useEffect(() => {
    QRCode.toDataURL(table.scan_url, { width: 220, margin: 2, color: { dark: '#1e1b4b', light: '#ffffff' } })
      .then(setDataUrl)
      .catch(() => setDataUrl(null))
  }, [table.scan_url])

  const handleCopy = () => {
    void navigator.clipboard.writeText(table.scan_url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // Build a printable A4 PDF: table name heading, a high-res QR, and a caption.
  const handleExportPdf = async () => {
    setExporting(true)
    try {
      const hiRes = await QRCode.toDataURL(table.scan_url, {
        width: 600,
        margin: 2,
        color: { dark: '#1e1b4b', light: '#ffffff' },
      })
      const doc = new jsPDF({ unit: 'mm', format: 'a4' })
      const pageW = doc.internal.pageSize.getWidth()
      const qrSize = 110
      const qrX = (pageW - qrSize) / 2

      doc.setFont('helvetica', 'bold')
      doc.setFontSize(26)
      doc.text(`Table ${table.name}`, pageW / 2, 45, { align: 'center' })

      doc.addImage(hiRes, 'PNG', qrX, 60, qrSize, qrSize)

      doc.setFont('helvetica', 'normal')
      doc.setFontSize(15)
      doc.text('Scan to view the menu & order', pageW / 2, 185, { align: 'center' })

      doc.save(`table-${table.name}.pdf`)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Table {table.name}</h3>
          <button className={styles.modalClose} onClick={onClose}>×</button>
        </div>

        <div className={styles.qrWrap}>
          {dataUrl
            ? <img src={dataUrl} alt={`QR code for table ${table.name}`} className={styles.qrImage} />
            : <div className={styles.qrPlaceholder}>Generating…</div>
          }
        </div>

        <div className={styles.scanLinkSection}>
          <p className={styles.scanLinkLabel}>Scan link</p>
          <div className={styles.scanLinkRow}>
            <a
              href={table.scan_url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.scanLink}
            >
              {table.scan_url}
            </a>
            <button className={styles.btnCopy} onClick={handleCopy}>
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>

        <button
          className={styles.btnExportPdf}
          onClick={() => void handleExportPdf()}
          disabled={exporting}
        >
          {exporting ? 'Preparing…' : '⬇ Export as PDF'}
        </button>
      </div>
    </div>
  )
}

// ── Edit row ──────────────────────────────────────────────────────────────────

interface EditRowProps {
  table: TableResponse
  onClose: () => void
}

function EditRow({ table, onClose }: EditRowProps) {
  const [name, setName] = useState(table.name)
  const [updateTable, { isLoading }] = useUpdateTableMutation()
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    setError(null)
    if (!name.trim()) return
    try {
      await updateTable({ id: table.id, name: name.trim() }).unwrap()
      onClose()
    } catch (e) {
      setError(errDetail(e))
    }
  }

  return (
    <>
      <input
        className={styles.inlineInput}
        value={name}
        onChange={(e) => setName(e.target.value)}
        maxLength={100}
        autoFocus
      />
      {error && <span className={styles.inlineError}>{error}</span>}
      <button className={styles.btnSave} onClick={() => void handleSave()} disabled={isLoading || !name.trim()}>
        {isLoading ? '…' : 'Save'}
      </button>
      <button className={styles.btnCancel} onClick={onClose}>Cancel</button>
    </>
  )
}

// ── Create form ───────────────────────────────────────────────────────────────

function CreateTableModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [createTable, { isLoading }] = useCreateTableMutation()
  const [error, setError] = useState<string | null>(null)
  useOnEscape(onClose)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) return
    try {
      await createTable({ name: name.trim() }).unwrap()
      onClose()
    } catch (e) {
      setError(errDetail(e))
    }
  }

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Add table</h3>
          <button className={styles.modalClose} type="button" onClick={onClose}>×</button>
        </div>
        <form className={styles.modalForm} onSubmit={(e) => void handleCreate(e)}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="table-name">Table name</label>
            <input
              id="table-name"
              className={styles.input}
              type="text"
              placeholder="e.g. T-01"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              required
              autoFocus
            />
          </div>
          {error && <p className={styles.formError}>{error}</p>}
          <div className={styles.modalActions}>
            <button type="button" className={styles.btnCancel} onClick={onClose}>Cancel</button>
            <button type="submit" className={styles.btnAdd} disabled={isLoading || !name.trim()}>
              {isLoading ? 'Creating…' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminTables() {
  const { data: tables, isLoading, isError } = useListTablesQuery()
  const [deactivateTable] = useDeactivateTableMutation()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [qrModal, setQrModal] = useState<TableResponse | null>(null)
  const [viewing, setViewing] = useState<TableResponse | null>(null)

  const list = tables ?? []
  const paged = usePaginatedList(list, { searchText: (t) => t.name })

  if (isLoading) return <div className={styles.page}><p>Loading…</p></div>
  if (isError) return <div className={styles.page}><p className={styles.formError}>Failed to load tables.</p></div>

  return (
    <div className={styles.page}>
      {qrModal && <QRModal table={qrModal} onClose={() => setQrModal(null)} />}

      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Tables</h1>
        <div className={styles.headerRight}>
          <HeaderControls list={paged} placeholder="Search tables…" />
          <button className={styles.btnAddTop} onClick={() => setShowCreate(true)}>
            + Add Table
          </button>
        </div>
      </div>

      {showCreate && <CreateTableModal onClose={() => setShowCreate(false)} />}

      {viewing && (
        <ViewModal
          title={`Table ${viewing.name}`}
          onClose={() => setViewing(null)}
          rows={[
            { label: 'Name', value: viewing.name },
            { label: 'Active', value: viewing.is_active ? 'Yes' : 'No' },
            {
              label: 'Scan link',
              value: (
                <a href={viewing.scan_url} target="_blank" rel="noopener noreferrer" className={styles.scanLink}>
                  {viewing.scan_url}
                </a>
              ),
            },
          ]}
        />
      )}

      <SearchBar value={paged.search} onChange={paged.setSearch} placeholder="Search tables…" />

      {/* Mobile cards */}
      <div className={styles.cardGrid}>
        {paged.pageItems.map((t: TableResponse) => (
          <EntityCard
            key={t.id}
            showImage={false}
            title={t.name}
            status={{ label: t.is_active ? 'Active' : 'Inactive', tone: t.is_active ? 'ok' : 'muted' }}
            bodyExtra={<button className={styles.btnQrCard} onClick={() => setQrModal(t)}>Show QR</button>}
            onView={() => setViewing(t)}
            onEdit={t.is_active ? () => setEditingId(t.id) : undefined}
            onDelete={t.is_active ? () => void deactivateTable(t.id) : undefined}
          >
            {editingId === t.id && (
              <div className={styles.cardEdit}>
                <EditRow table={t} onClose={() => setEditingId(null)} />
              </div>
            )}
          </EntityCard>
        ))}
        {paged.total === 0 && (
          <p className={styles.empty}>{list.length === 0 ? 'No tables yet.' : 'No matches.'}</p>
        )}
      </div>

      <div className={styles.desktopOnly}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>QR Code</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {paged.pageItems.map((t: TableResponse) => (
            <tr key={t.id}>
              <td>
                {editingId === t.id ? (
                  <EditRow table={t} onClose={() => setEditingId(null)} />
                ) : (
                  t.name
                )}
              </td>
              <td>
                <span className={t.is_active ? styles.badgeActive : styles.badgeInactive}>
                  {t.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td>
                <button className={styles.btnQr} onClick={() => setQrModal(t)}>
                  Show QR
                </button>
              </td>
              <td className={styles.actions}>
                {editingId !== t.id && (
                  <>
                    <IconAction kind="view" onClick={() => setViewing(t)} title="View" />
                    <IconAction kind="edit" onClick={() => setEditingId(t.id)} title="Rename" disabled={!t.is_active} />
                    {t.is_active && (
                      <IconAction kind="delete" onClick={() => void deactivateTable(t.id)} title="Deactivate" />
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
          {paged.total === 0 && (
            <tr>
              <td colSpan={4} className={styles.empty}>{list.length === 0 ? 'No tables yet.' : 'No matches.'}</td>
            </tr>
          )}
        </tbody>
      </table>
      </div>

      <PageNav list={paged} />
    </div>
  )
}
