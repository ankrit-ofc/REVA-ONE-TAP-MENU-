import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useMenu } from '@/features/menu/useMenu'
import { useCart } from '@/features/cart/useCart'
import { makeCartKey } from '@/features/cart/cartSlice'
import Button from '@/components/common/Button'
import Loader from '@/components/common/Loader'
import TableArView from '@/components/customer/TableArView'
import { formatPrice } from '@/lib/currency'
import styles from './ProductDetail.module.css'

const CURRENCY = 'NPR'
const DESCRIPTION_WORD_LIMIT = 5

const detailFormSchema = z.object({
  variantId: z.string().uuid().nullable(),
  addonIds: z.array(z.string().uuid()),
  quantity: z.number().int().min(1).max(99),
})

/** Show at most the first N words of the description (with an ellipsis if trimmed). */
function shortDescription(text: string, limit = DESCRIPTION_WORD_LIMIT): string {
  const words = text.trim().split(/\s+/)
  return words.length <= limit ? words.join(' ') : `${words.slice(0, limit).join(' ')}…`
}

export default function ProductDetail() {
  const { productId } = useParams<{ productId: string }>()
  const navigate = useNavigate()
  const { findProduct, isLoading } = useMenu()
  const { addItem } = useCart()

  const product = productId ? findProduct(productId) : undefined

  const [variantId, setVariantId] = useState<string | null>(null)
  const [addonIds, setAddonIds] = useState<string[]>([])
  const [quantity, setQuantity] = useState(1)
  const [orderMode, setOrderMode] = useState<'idle' | 'qty'>('idle')
  const [validationError, setValidationError] = useState<string | null>(null)

  if (isLoading) return <Loader fullscreen message="Loading…" />

  if (!product) {
    return (
      <div className={styles.errorState}>
        <p>Product not found.</p>
        <button onClick={() => navigate(-1)} className={styles.backBtn}>
          ← Back to menu
        </button>
      </div>
    )
  }

  const selectedVariant = product.variants.find((v) => v.id === variantId)
  const selectedAddons = product.addons.filter((a) => addonIds.includes(a.id))
  const addonTotal = selectedAddons.reduce((s, a) => s + a.price, 0)
  const unitPrice = selectedVariant?.price ?? product.base_price
  const linePrice = (unitPrice + addonTotal) * quantity

  function toggleAddon(id: string) {
    setAddonIds((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id],
    )
  }

  // First tap on "Add to Order": validate the variant, then reveal the quantity stepper.
  function startOrder() {
    setValidationError(null)
    if (product!.has_variants && !variantId) {
      setValidationError('Please choose a size or variant.')
      return
    }
    setOrderMode('qty')
  }

  // Tap the tick: commit the line to the cart and go to the cart.
  function confirmOrder() {
    setValidationError(null)

    const parsed = detailFormSchema.safeParse({
      variantId: variantId ?? null,
      addonIds,
      quantity,
    })

    if (!parsed.success) {
      setValidationError(parsed.error.issues[0]?.message ?? 'Invalid selection.')
      return
    }

    addItem({
      key: makeCartKey(product!.id, variantId, addonIds),
      productId: product!.id,
      productName: product!.name,
      variantId: variantId,
      variantName: selectedVariant?.name ?? null,
      addonIds,
      addonNames: selectedAddons.map((a) => a.name),
      addonPriceTotal: addonTotal,
      quantity,
      specialInstructions: '',
      unitPrice,
      taxRate: product!.tax_rate,
    })

    navigate('/cart')
  }

  return (
    <div className={styles.page}>
      <button onClick={() => navigate(-1)} className={styles.backBtn} aria-label="Back">
        ← Back
      </button>

      {product.image_url && (
        <img src={product.image_url} alt={product.name} className={styles.image} />
      )}

      <div className={styles.body}>
        <h1 className={styles.name}>{product.name}</h1>
        <p className={styles.basePrice}>
          {formatPrice(product.base_price, CURRENCY)}
        </p>

        {product.description && (
          <p className={styles.description}>{shortDescription(product.description)}</p>
        )}

        {/* Variant selection */}
        {product.has_variants && product.variants.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>
              Choose size <span className={styles.required}>*</span>
            </h2>
            <div className={styles.optionGroup}>
              {product.variants.map((v) => (
                <button
                  key={v.id}
                  className={`${styles.optionBtn} ${variantId === v.id ? styles.optionSelected : ''}`}
                  onClick={() => setVariantId(v.id)}
                  aria-pressed={variantId === v.id}
                >
                  <span>{v.name}</span>
                  <span className={styles.optionPrice}>
                    {formatPrice(v.price, CURRENCY)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Addon selection */}
        {product.allows_addons && product.addons.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Add-ons</h2>
            <div className={styles.optionGroup}>
              {product.addons.map((a) => (
                <button
                  key={a.id}
                  className={`${styles.optionBtn} ${addonIds.includes(a.id) ? styles.optionSelected : ''}`}
                  onClick={() => toggleAddon(a.id)}
                  aria-pressed={addonIds.includes(a.id)}
                >
                  <span>{a.name}</span>
                  <span className={styles.optionPrice}>
                    + {formatPrice(a.price, CURRENCY)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {validationError && (
          <p role="alert" className={styles.error}>
            {validationError}
          </p>
        )}

        {/* Actions: order, then view in AR */}
        <div className={styles.actions}>
          {orderMode === 'idle' ? (
            <Button
              onClick={startOrder}
              style={{ width: '100%', fontSize: '1rem', padding: '0.9rem' }}
            >
              Add to Order · {formatPrice(linePrice, CURRENCY)}
            </Button>
          ) : (
            <div className={styles.orderRow}>
              <div className={styles.qtyRow}>
                <button
                  className={styles.qtyBtn}
                  onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                  aria-label="Decrease quantity"
                >
                  −
                </button>
                <span className={styles.qtyNum}>{quantity}</span>
                <button
                  className={styles.qtyBtn}
                  onClick={() => setQuantity((q) => Math.min(99, q + 1))}
                  aria-label="Increase quantity"
                >
                  +
                </button>
              </div>
              <button
                className={styles.confirmBtn}
                onClick={confirmOrder}
                aria-label={`Confirm order, ${formatPrice(linePrice, CURRENCY)}`}
              >
                ✓
              </button>
            </div>
          )}

          {/* Per-dish AR — only for products with a published model. Hidden-preloaded so
              the button launches AR on the second, real tap. */}
          {product.model_glb_url && (
            <TableArView
              src={product.model_glb_url}
              iosSrc={product.model_usdz_url ?? undefined}
              alt={product.name}
              className={styles.tableBtn}
            />
          )}
        </div>
      </div>
    </div>
  )
}
