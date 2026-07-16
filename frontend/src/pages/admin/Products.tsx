import { useState, useRef } from 'react'
import {
  useListProductsQuery,
  useListCategoriesQuery,
  useListAddonsQuery,
  useCreateProductMutation,
  useUpdateProductMutation,
  useSoftDeleteProductMutation,
  useUploadProductImageMutation,
  useListVariantsQuery,
  useCreateVariantMutation,
  useUpdateVariantMutation,
  useSoftDeleteVariantMutation,
  useListProductAddonsQuery,
  useMapAddonMutation,
  useUnmapAddonMutation,
} from '@/features/admin/adminApi'
import type { ProductResponse, VariantResponse, FoodType } from '@/lib/schemas/admin'
import EntityCard from '@/components/admin/EntityCard'
import Model3DForm from '@/components/admin/Model3DForm'
import { indentedCategoryOptions } from '@/features/menu/categoryTree'
import IconAction from '@/components/admin/IconAction'
import ViewModal from '@/components/admin/ViewModal'
import SearchBar from '@/components/admin/SearchBar'
import HeaderControls from '@/components/admin/HeaderControls'
import PageNav from '@/components/admin/PageNav'
import { usePaginatedList } from '@/components/admin/usePaginatedList'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './AdminTable.module.css'
import ps from './Products.module.css'

const MAX_FILE_MB = 25
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

const FOOD_TYPES: { value: FoodType; label: string }[] = [
  { value: 'VEG', label: 'Veg' },
  { value: 'NON_VEG', label: 'Non-veg' },
  { value: 'EGG', label: 'Egg' },
  { value: 'BEVERAGE', label: 'Beverage' },
  { value: 'SMOKE', label: 'Smoke' },
]

const VEG_BADGE_CLASS: Record<FoodType, string> = {
  VEG: ps.vegVeg,
  NON_VEG: ps.vegNonVeg,
  EGG: ps.vegEgg,
  BEVERAGE: ps.vegBeverage,
  SMOKE: ps.vegSmoke,
}

/** Trim a description to at most `max` words, appending an ellipsis if cut. */
function truncateWords(text: string, max = 9): string {
  const words = text.trim().split(/\s+/)
  if (words.length <= max) return text.trim()
  return words.slice(0, max).join(' ') + '…'
}

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Request failed'
}

// ── Veg/Non-veg/Egg indicator ──────────────────────────────────────────────────

function VegBadge({ foodType }: { foodType: FoodType }) {
  const cls = VEG_BADGE_CLASS[foodType] ?? ps.vegNonVeg
  const label = FOOD_TYPES.find((f) => f.value === foodType)?.label ?? foodType
  return (
    <span className={`${ps.vegBadge} ${cls}`}>
      <span className={ps.vegSquare} />
      {label}
    </span>
  )
}

function validateImage(file: File): string | null {
  if (!ALLOWED_TYPES.includes(file.type)) return 'Only JPEG, PNG, or WebP images allowed.'
  if (file.size > MAX_FILE_MB * 1024 * 1024) return `Image must be under ${MAX_FILE_MB} MB.`
  return null
}

// ── Variant editor (edit mode — live against an existing product) ───────────────

function VariantRow({ productId, variant }: { productId: string; variant: VariantResponse }) {
  const [name, setName] = useState(variant.name)
  const [price, setPrice] = useState(String(variant.price))
  const [updateVariant, { isLoading }] = useUpdateVariantMutation()
  const [deleteVariant] = useSoftDeleteVariantMutation()

  const dirty = name !== variant.name || price !== String(variant.price)
  const save = () => {
    const p = parseFloat(price)
    if (!name.trim() || isNaN(p) || p < 0) return
    void updateVariant({ productId, variantId: variant.id, name: name.trim(), price: p })
  }

  return (
    <div className={ps.vRow}>
      <input className={`${styles.input} ${ps.vName}`} value={name} onChange={(e) => setName(e.target.value.slice(0, 60))} maxLength={60} />
      <input className={`${styles.input} ${ps.vPrice}`} type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
      <button type="button" className={ps.btnSm} disabled={!dirty || isLoading} onClick={save}>Save</button>
      <button type="button" className={ps.btnRemove} onClick={() => void deleteVariant({ productId, variantId: variant.id })}>✕</button>
    </div>
  )
}

function VariantsEditor({ productId }: { productId: string }) {
  const { data: variants } = useListVariantsQuery(productId)
  const [createVariant, { isLoading }] = useCreateVariantMutation()
  const [name, setName] = useState('')
  const [price, setPrice] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const active = (variants ?? []).filter((v) => v.is_active)

  const add = async () => {
    setErr(null)
    const p = parseFloat(price)
    if (!name.trim() || isNaN(p) || p < 0) { setErr('Enter a name and valid price.'); return }
    try {
      await createVariant({ productId, name: name.trim(), price: p }).unwrap()
      setName(''); setPrice('')
    } catch (e) { setErr(errDetail(e)) }
  }

  return (
    <div className={ps.subSection}>
      <span className={ps.subTitle}>Variants (customer picks one; its price replaces the base price)</span>
      {active.map((v) => <VariantRow key={v.id} productId={productId} variant={v} />)}
      {active.length === 0 && <span className={ps.muted}>No variants yet.</span>}
      <div className={ps.vRow}>
        <input className={`${styles.input} ${ps.vName}`} placeholder="e.g. Large" value={name} onChange={(e) => setName(e.target.value.slice(0, 60))} maxLength={60} />
        <input className={`${styles.input} ${ps.vPrice}`} type="number" min="0" step="0.01" placeholder="Price" value={price} onChange={(e) => setPrice(e.target.value)} />
        <button type="button" className={ps.btnSmPrimary} disabled={isLoading} onClick={() => void add()}>+ Add</button>
      </div>
      {err && <span className={styles.inlineError}>{err}</span>}
    </div>
  )
}

// ── Add-on mapping editor (edit mode) ───────────────────────────────────────────

function AddonsEditor({ productId }: { productId: string }) {
  const { data: mapped } = useListProductAddonsQuery(productId)
  const { data: pool } = useListAddonsQuery()
  const [mapAddon] = useMapAddonMutation()
  const [unmapAddon] = useUnmapAddonMutation()
  const [sel, setSel] = useState('')

  const mappedIds = new Set((mapped ?? []).map((m) => m.addon_id))
  const available = (pool ?? []).filter((a) => a.is_active && !mappedIds.has(a.id))

  return (
    <div className={ps.subSection}>
      <span className={ps.subTitle}>Add-ons (optional paid extras; each adds to the price)</span>
      {(mapped ?? []).map((m) => (
        <div key={m.id} className={ps.vRow}>
          <span className={ps.vName}>{m.addon.name} — NPR {m.addon.price.toFixed(2)}</span>
          <button type="button" className={ps.btnRemove} onClick={() => void unmapAddon({ productId, addonId: m.addon_id })}>✕</button>
        </div>
      ))}
      {(mapped ?? []).length === 0 && <span className={ps.muted}>No add-ons mapped.</span>}
      <div className={ps.vRow}>
        <select className={`${styles.input} ${ps.vName}`} value={sel} onChange={(e) => setSel(e.target.value)}>
          <option value="">Map an add-on…</option>
          {available.map((a) => <option key={a.id} value={a.id}>{a.name} (NPR {a.price.toFixed(2)})</option>)}
        </select>
        <button type="button" className={ps.btnSmPrimary} disabled={!sel} onClick={() => { if (sel) { void mapAddon({ productId, addonId: sel }); setSel('') } }}>+ Map</button>
      </div>
      {(pool ?? []).filter((a) => a.is_active).length === 0 && (
        <span className={ps.muted}>No add-ons in the pool yet — create them on the Add-ons page.</span>
      )}
    </div>
  )
}

// ── Add / Edit product modal ────────────────────────────────────────────────────

interface ProductModalProps {
  product?: ProductResponse
  categories: { id: string; name: string; is_active: boolean; parent_id: string | null }[]
  onClose: () => void
}

function ProductModal({ product, categories, onClose }: ProductModalProps) {
  const isEdit = product != null
  const [createProduct, { isLoading: creating }] = useCreateProductMutation()
  const [updateProduct, { isLoading: updating }] = useUpdateProductMutation()
  const [createVariant] = useCreateVariantMutation()
  const [mapAddon] = useMapAddonMutation()
  const [uploadImage, { isLoading: uploading }] = useUploadProductImageMutation()
  const { data: pool } = useListAddonsQuery()
  useOnEscape(onClose)

  const [form, setForm] = useState({
    category_id: product?.category_id ?? '',
    name: product?.name ?? '',
    description: product?.description ?? '',
    base_price: product ? String(product.base_price) : '',
    tax_rate: product ? String(product.tax_rate) : '0',
    food_type: (product?.food_type ?? 'NON_VEG') as FoodType,
    is_available: product?.is_available ?? true,
    has_variants: product?.has_variants ?? false,
    allows_addons: product?.allows_addons ?? false,
  })
  // Create-mode drafts (variants + add-ons are persisted after the product exists).
  const [variantDrafts, setVariantDrafts] = useState<{ name: string; price: string }[]>([])
  const [selectedAddonIds, setSelectedAddonIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  // Image: edit mode uploads immediately; add mode stashes the File until the
  // product exists, then uploads it after createProduct.
  const fileRef = useRef<HTMLInputElement>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(product?.image_url ?? null)

  const handleImagePick = async (file: File) => {
    setError(null)
    const v = validateImage(file)
    if (v) { setError(v); return }
    setImagePreview(URL.createObjectURL(file))
    if (isEdit) {
      try { await uploadImage({ productId: product.id, file }).unwrap() }
      catch (e) { setError(errDetail(e)) }
    } else {
      setPendingFile(file)
    }
  }

  const activeCategories = categories.filter((c) => c.is_active)
  const saving = creating || updating

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!form.category_id) { setError('Select a category.'); return }
    if (!form.name.trim()) { setError('Product name is required.'); return }
    // Variant products are priced by their variants — base_price isn't charged,
    // so we don't ask for it and send 0. Simple products require a valid price.
    let price = 0
    if (!form.has_variants) {
      price = parseFloat(form.base_price)
      if (isNaN(price) || price < 0) { setError('Invalid base price.'); return }
    }
    const tax = parseFloat(form.tax_rate)
    if (isNaN(tax) || tax < 0 || tax > 100) { setError('Tax rate must be 0–100.'); return }

    const payload = {
      category_id: form.category_id,
      name: form.name.trim(),
      description: form.description.trim(),
      base_price: price,
      tax_rate: tax,
      food_type: form.food_type,
      is_available: form.is_available,
      has_variants: form.has_variants,
      allows_addons: form.allows_addons,
    }

    try {
      if (isEdit) {
        await updateProduct({ id: product.id, ...payload }).unwrap()
      } else {
        const created = await createProduct(payload).unwrap()
        if (form.has_variants) {
          for (const d of variantDrafts) {
            const p = parseFloat(d.price)
            if (d.name.trim() && !isNaN(p) && p >= 0) {
              await createVariant({ productId: created.id, name: d.name.trim(), price: p }).unwrap()
            }
          }
        }
        if (form.allows_addons) {
          for (const aid of selectedAddonIds) {
            await mapAddon({ productId: created.id, addonId: aid }).unwrap()
          }
        }
        if (pendingFile) {
          await uploadImage({ productId: created.id, file: pendingFile }).unwrap()
        }
      }
      onClose()
    } catch (err) {
      setError(errDetail(err))
    }
  }

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm({ ...form, [k]: v })

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal} style={{ width: 560, maxWidth: '100%' }}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>{isEdit ? 'Edit Product' : 'Add Product'}</h3>
          <button className={styles.modalClose} type="button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={(e) => void submit(e)} className={ps.modalBody}>
          <div className={ps.formRow}>
            <label className={ps.field}>
              Category
              <select className={styles.input} value={form.category_id} onChange={(e) => set('category_id', e.target.value)}>
                <option value="">Select category…</option>
                {indentedCategoryOptions(activeCategories).map(({ cat, depth }) => (
                  <option key={cat.id} value={cat.id}>
                    {`${'  '.repeat(depth)}${depth > 0 ? '└ ' : ''}${cat.name}`}
                  </option>
                ))}
              </select>
            </label>
            <label className={ps.field}>
              Food Type
              <select className={styles.input} value={form.food_type} onChange={(e) => set('food_type', e.target.value as FoodType)}>
                {FOOD_TYPES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
            </label>
          </div>

          <label className={ps.field}>
            Name
            <input className={styles.input} value={form.name} onChange={(e) => set('name', e.target.value.slice(0, 120))} maxLength={120} placeholder="Product name" />
          </label>

          <label className={ps.field}>
            Short description
            <input className={styles.input} value={form.description} onChange={(e) => set('description', e.target.value.slice(0, 255))} maxLength={255} placeholder="e.g. Grilled chicken patty with lettuce and house sauce" />
          </label>

          {/* Image */}
          <div className={ps.field}>
            Image
            <div className={ps.vRow}>
              {imagePreview
                ? <img src={imagePreview} alt="" className={styles.imagePreview} />
                : <div className={styles.imagePlaceholder}>🍱</div>}
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                style={{ display: 'none' }}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleImagePick(f) }}
              />
              <button type="button" className={ps.btnSm} disabled={uploading} onClick={() => fileRef.current?.click()}>
                {uploading ? 'Uploading…' : imagePreview ? 'Replace image' : 'Upload image'}
              </button>
            </div>
            <span className={ps.hint}>Any size or shape (up to 25 MB) — auto-cropped to a square.</span>
          </div>

          <div className={ps.formRow}>
            {!form.has_variants && (
              <label className={ps.field}>
                Base Price (NPR)
                <input className={styles.input} type="number" min="0" step="0.01" value={form.base_price} onChange={(e) => set('base_price', e.target.value)} placeholder="0.00" />
              </label>
            )}
            <label className={ps.field}>
              Tax Rate (%)
              <input className={styles.input} type="number" min="0" max="100" step="0.01" value={form.tax_rate} onChange={(e) => set('tax_rate', e.target.value)} />
            </label>
          </div>

          <div className={ps.checkRow}>
            <label className={ps.checkLabel}>
              <input type="checkbox" checked={form.is_available} onChange={(e) => set('is_available', e.target.checked)} />
              Available
            </label>
            <label className={ps.checkLabel}>
              <input type="checkbox" checked={form.has_variants} onChange={(e) => set('has_variants', e.target.checked)} />
              Has Variants
            </label>
            <label className={ps.checkLabel}>
              <input type="checkbox" checked={form.allows_addons} onChange={(e) => set('allows_addons', e.target.checked)} />
              Allows Add-ons
            </label>
          </div>

          {/* Variants */}
          {form.has_variants && (isEdit
            ? <VariantsEditor productId={product.id} />
            : (
              <div className={ps.subSection}>
                <span className={ps.subTitle}>Variants (customer picks one; its price replaces the base price)</span>
                {variantDrafts.map((d, i) => (
                  <div key={i} className={ps.vRow}>
                    <input className={`${styles.input} ${ps.vName}`} placeholder="e.g. Large" value={d.name}
                      onChange={(e) => setVariantDrafts(variantDrafts.map((x, j) => j === i ? { ...x, name: e.target.value.slice(0, 60) } : x))} />
                    <input className={`${styles.input} ${ps.vPrice}`} type="number" min="0" step="0.01" placeholder="Price" value={d.price}
                      onChange={(e) => setVariantDrafts(variantDrafts.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} />
                    <button type="button" className={ps.btnRemove} onClick={() => setVariantDrafts(variantDrafts.filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
                <button type="button" className={ps.btnSm} onClick={() => setVariantDrafts([...variantDrafts, { name: '', price: '' }])}>+ Add variant</button>
              </div>
            ))}

          {/* Add-ons */}
          {form.allows_addons && (isEdit
            ? <AddonsEditor productId={product.id} />
            : (
              <div className={ps.subSection}>
                <span className={ps.subTitle}>Add-ons (optional paid extras; each adds to the price)</span>
                {(pool ?? []).filter((a) => a.is_active).map((a) => (
                  <label key={a.id} className={ps.checkLabel}>
                    <input type="checkbox" checked={selectedAddonIds.includes(a.id)}
                      onChange={(e) => setSelectedAddonIds(e.target.checked ? [...selectedAddonIds, a.id] : selectedAddonIds.filter((x) => x !== a.id))} />
                    {a.name} — NPR {a.price.toFixed(2)}
                  </label>
                ))}
                {(pool ?? []).filter((a) => a.is_active).length === 0 && (
                  <span className={ps.muted}>No add-ons in the pool yet — create them on the Add-ons page.</span>
                )}
              </div>
            ))}

          {/* 3D model (AR) — edit mode only; needs a saved product to attach views to. */}
          {isEdit
            ? <Model3DForm productId={product.id} />
            : (
              <div className={ps.subSection}>
                <span className={ps.subTitle}>3D Model (AR)</span>
                <span className={ps.muted}>Save the product first, then reopen it to add a 3D model.</span>
              </div>
            )}

          {error && <p className={styles.formError}>{error}</p>}

          <div className={styles.modalActions}>
            <button type="button" className={styles.btnCancel} onClick={onClose}>Cancel</button>
            <button type="submit" className={styles.btnAdd} disabled={saving}>
              {saving ? 'Saving…' : isEdit ? 'Save' : 'Create Product'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────────

export default function AdminProducts() {
  const { data: products, isLoading, isError } = useListProductsQuery()
  const { data: categories } = useListCategoriesQuery()
  const [updateProduct] = useUpdateProductMutation()
  const [softDelete] = useSoftDeleteProductMutation()

  const [showAdd, setShowAdd] = useState(false)
  const [editing, setEditing] = useState<ProductResponse | null>(null)
  const [viewing, setViewing] = useState<ProductResponse | null>(null)
  const [specialsOnly, setSpecialsOnly] = useState(false)

  const allProducts = products ?? []
  const productList = specialsOnly ? allProducts.filter((p) => p.is_todays_special) : allProducts
  const paged = usePaginatedList(productList, {
    searchText: (p) => `${p.name} ${p.description ?? ''}`,
  })

  if (isLoading) return <div className={styles.state}>Loading products…</div>
  if (isError) return <div className={styles.state} style={{ color: '#dc2626' }}>Failed to load products.</div>

  const cats = categories ?? []
  const catName = (id: string) => cats.find((c) => c.id === id)?.name ?? '—'

  const handleDelete = (p: ProductResponse) => {
    if (window.confirm(`Delete "${p.name}"?\n\nIt will be removed from the menu. This can't be undone from here.`)) {
      void softDelete(p.id)
    }
  }

  return (
    <div className={styles.root}>
      {showAdd && <ProductModal categories={cats} onClose={() => setShowAdd(false)} />}
      {editing && <ProductModal product={editing} categories={cats} onClose={() => setEditing(null)} />}
      {viewing && (
        <ViewModal
          title={viewing.name}
          onClose={() => setViewing(null)}
          rows={[
            { label: 'Name', value: viewing.name },
            { label: 'Description', value: viewing.description || '—' },
            { label: 'Category', value: catName(viewing.category_id) },
            { label: 'Price', value: viewing.has_variants ? 'By variant' : `NPR ${Number(viewing.base_price).toFixed(2)}` },
            { label: 'Tax', value: `${Number(viewing.tax_rate).toFixed(1)}%` },
            { label: 'Type', value: <VegBadge foodType={viewing.food_type} /> },
            { label: 'Available', value: viewing.is_available ? 'Yes' : 'No' },
            { label: "Today's Special", value: viewing.is_todays_special ? 'Yes ⭐' : 'No' },
            { label: 'Has Variants', value: viewing.has_variants ? 'Yes' : 'No' },
            { label: 'Allows Add-ons', value: viewing.allows_addons ? 'Yes' : 'No' },
            {
              label: 'Image',
              value: viewing.image_url
                ? <img src={viewing.image_url} alt="" className={styles.imagePreview} />
                : '—',
            },
          ]}
        />
      )}

      <div className={ps.header}>
        <h1 className={styles.title}>Products</h1>
        <div className={styles.headerRight}>
          <button
            className={`${ps.specialFilter} ${specialsOnly ? ps.specialFilterActive : ''}`}
            onClick={() => setSpecialsOnly(!specialsOnly)}
            aria-pressed={specialsOnly}
            title="Show only products featured as Today's Special"
          >
            ⭐ Today&rsquo;s Special
          </button>
          <HeaderControls list={paged} placeholder="Search products…" />
          <button className={styles.btnAdd} onClick={() => setShowAdd(true)}>+ Add Product</button>
        </div>
      </div>

      <SearchBar value={paged.search} onChange={paged.setSearch} placeholder="Search products…" />

      {/* Mobile cards */}
      <div className={styles.cardGrid}>
        {paged.pageItems.map((p) => (
          <EntityCard
            key={p.id}
            image={p.image_url}
            title={p.is_todays_special ? `⭐ ${p.name}` : p.name}
            subtitle={p.description ? truncateWords(p.description) : undefined}
            status={{ label: p.is_available ? 'Available' : 'Hidden', tone: p.is_available ? 'ok' : 'warn' }}
            onView={() => setViewing(p)}
            onEdit={() => setEditing(p)}
            onDelete={() => handleDelete(p)}
          />
        ))}
        {paged.total === 0 && (
          <p className={styles.empty}>{allProducts.length === 0 ? 'No products yet.' : 'No matches.'}</p>
        )}
      </div>

      <div className={`${styles.tableWrap} ${styles.desktopOnly}`}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Image</th>
              <th>Name</th>
              <th>Category</th>
              <th>Price</th>
              <th>Tax</th>
              <th>Type</th>
              <th>Available</th>
              <th>Special</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {paged.pageItems.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.image_url
                    ? <img src={p.image_url} alt={p.name} className={styles.imagePreview} />
                    : <div className={styles.imagePlaceholder}>🍱</div>}
                </td>
                <td>
                  {p.name}{p.has_variants && <span className={ps.muted}> · variants</span>}
                  {p.description && <div className={ps.muted}>{truncateWords(p.description)}</div>}
                </td>
                <td>{catName(p.category_id)}</td>
                <td>NPR {Number(p.base_price).toFixed(2)}</td>
                <td>{Number(p.tax_rate).toFixed(1)}%</td>
                <td><VegBadge foodType={p.food_type} /></td>
                <td>
                  <button
                    className={p.is_available ? ps.toggleOn : ps.toggleOff}
                    onClick={() => void updateProduct({ id: p.id, is_available: !p.is_available })}
                  >
                    {p.is_available ? 'Yes' : 'No'}
                  </button>
                </td>
                <td>
                  <button
                    className={`${ps.starBtn} ${p.is_todays_special ? ps.starOn : ''}`}
                    onClick={() => void updateProduct({ id: p.id, is_todays_special: !p.is_todays_special })}
                    title={p.is_todays_special ? "Remove from Today's Special" : "Feature as Today's Special"}
                    aria-pressed={p.is_todays_special}
                    aria-label={p.is_todays_special ? "Remove from Today's Special" : "Feature as Today's Special"}
                  >
                    ⭐
                  </button>
                </td>
                <td className={styles.actions}>
                  <IconAction kind="view" onClick={() => setViewing(p)} title="View" />
                  <IconAction kind="edit" onClick={() => setEditing(p)} title="Edit" />
                  <IconAction kind="delete" onClick={() => handleDelete(p)} title="Delete" />
                </td>
              </tr>
            ))}
            {paged.total === 0 && (
              <tr><td colSpan={9} className={styles.emptyRow}>{allProducts.length === 0 ? 'No products yet.' : 'No matches.'}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <PageNav list={paged} />
    </div>
  )
}
