import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { usePreviewProductImportMutation, useCommitProductImportMutation } from '@/features/admin/adminApi'
import type { ImportPreviewResponse, ImportCommitResponse } from '@/lib/schemas/admin'
import styles from './AdminTable.module.css'
import ps from './ProductImport.module.css'

const TEMPLATE_CSV =
  'category,name,short_description,food_type,base_price,tax_rate,available\n' +
  'Momos,Chicken Momo,Steamed dumplings with house sauce,Non-veg,250.00,13,true\n'

function downloadTemplate() {
  const blob = new Blob([TEMPLATE_CSV], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'product-import-template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: unknown } }).data
    const detail = d?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String((detail as { message?: unknown }).message ?? 'Request failed')
    }
  }
  return 'Request failed'
}

export default function AdminProductImport() {
  const [file, setFile] = useState<File | null>(null)
  const [previewResult, setPreviewResult] = useState<ImportPreviewResponse | null>(null)
  const [commitResult, setCommitResult] = useState<ImportCommitResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const [runPreview, { isLoading: previewing }] = usePreviewProductImportMutation()
  const [runCommit, { isLoading: committing }] = useCommitProductImportMutation()

  const pickFile = (f: File) => {
    setFile(f)
    setPreviewResult(null)
    setCommitResult(null)
    setError(null)
  }

  const handlePreview = async () => {
    if (!file) return
    setError(null)
    setCommitResult(null)
    try {
      const result = await runPreview(file).unwrap()
      setPreviewResult(result)
    } catch (e) {
      setPreviewResult(null)
      setError(errDetail(e))
    }
  }

  const handleCommit = async () => {
    if (!file || !previewResult || previewResult.errors.length > 0) return
    setError(null)
    try {
      const result = await runCommit(file).unwrap()
      setCommitResult(result)
      setPreviewResult(null) // force a fresh preview before importing again
    } catch (e) {
      setError(errDetail(e))
    }
  }

  const canConfirm = !!previewResult && previewResult.errors.length === 0 && !committing

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Bulk Import Products</h1>
        <div className={styles.headerRight}>
          <button className={styles.btnAddTop} type="button" onClick={downloadTemplate}>
            Download CSV template
          </button>
          <Link to="/admin/products" className={ps.backLink}>← Back to Products</Link>
        </div>
      </div>

      <p className={ps.intro}>
        Upload a CSV of products (e.g. extracted from a photo of a paper menu), preview exactly
        what will be created, then confirm. Images aren&apos;t imported — add those afterward from
        the Products page.
      </p>

      <div className={ps.dropzone}>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          style={{ display: 'none' }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f) }}
        />
        <button type="button" className={styles.btnAddTop} onClick={() => fileRef.current?.click()}>
          {file ? 'Choose a different file' : 'Choose CSV file'}
        </button>
        {file && <span className={ps.fileName}>{file.name}</span>}
        <button
          type="button"
          className={styles.btnAdd}
          disabled={!file || previewing}
          onClick={() => void handlePreview()}
        >
          {previewing ? 'Checking…' : 'Preview'}
        </button>
      </div>

      {error && <p className={styles.formError}>{error}</p>}

      {previewResult && (
        <>
          <div className={ps.summaryRow}>
            <div className={ps.summaryTile}>
              <span className={ps.summaryValue}>{previewResult.valid_rows}</span>
              <span className={ps.summaryLabel}>Valid rows</span>
            </div>
            <div className={ps.summaryTile}>
              <span className={ps.summaryValue}>{previewResult.products_to_create}</span>
              <span className={ps.summaryLabel}>Products to create</span>
            </div>
            <div className={ps.summaryTile}>
              <span className={ps.summaryValue}>{previewResult.duplicates_skipped}</span>
              <span className={ps.summaryLabel}>Duplicates skipped</span>
            </div>
            <div className={ps.summaryTile}>
              <span className={ps.summaryValue}>{previewResult.errors.length}</span>
              <span className={ps.summaryLabel}>Rows with errors</span>
            </div>
          </div>

          {(previewResult.new_categories.length > 0 || previewResult.existing_categories.length > 0) && (
            <div className={ps.categoriesRow}>
              {previewResult.new_categories.length > 0 && (
                <div className={ps.categoryGroup}>
                  <span className={ps.categoryGroupLabel}>New categories (will be created)</span>
                  <div className={ps.chipRow}>
                    {previewResult.new_categories.map((c) => (
                      <span key={c} className={ps.chipNew}>{c}</span>
                    ))}
                  </div>
                </div>
              )}
              {previewResult.existing_categories.length > 0 && (
                <div className={ps.categoryGroup}>
                  <span className={ps.categoryGroupLabel}>Existing categories (reused)</span>
                  <div className={ps.chipRow}>
                    {previewResult.existing_categories.map((c) => (
                      <span key={c} className={ps.chipExisting}>{c}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {previewResult.errors.length > 0 && (
            <div className={`${styles.tableWrap} ${ps.errorTableWrap}`}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Field</th>
                    <th>Problem</th>
                    <th>Value in CSV</th>
                  </tr>
                </thead>
                <tbody>
                  {previewResult.errors.map((e, i) => (
                    <tr key={i}>
                      <td>{e.row}</td>
                      <td>{e.field}</td>
                      <td>{e.message}</td>
                      <td className={ps.rawCell}>{e.raw || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className={ps.confirmRow}>
            {previewResult.errors.length > 0 ? (
              <span className={ps.blockedHint}>Fix the rows above and re-preview before you can import.</span>
            ) : (
              <span className={ps.readyHint}>
                Ready to create {previewResult.products_to_create} product
                {previewResult.products_to_create === 1 ? '' : 's'}
                {previewResult.new_categories.length > 0
                  ? ` and ${previewResult.new_categories.length} categor${previewResult.new_categories.length === 1 ? 'y' : 'ies'}`
                  : ''}.
              </span>
            )}
            <button
              type="button"
              className={styles.btnAddTop}
              disabled={!canConfirm}
              onClick={() => void handleCommit()}
            >
              {committing ? 'Importing…' : 'Confirm import'}
            </button>
          </div>
        </>
      )}

      {commitResult && (
        <div className={ps.successBanner}>
          Imported {commitResult.products_created} product{commitResult.products_created === 1 ? '' : 's'}
          {commitResult.categories_created > 0
            ? ` and created ${commitResult.categories_created} new categor${commitResult.categories_created === 1 ? 'y' : 'ies'}`
            : ''}.
          {commitResult.duplicates_skipped > 0 && ` ${commitResult.duplicates_skipped} duplicate row(s) were skipped.`}
          {' '}
          <Link to="/admin/products">View products →</Link>
        </div>
      )}
    </div>
  )
}
