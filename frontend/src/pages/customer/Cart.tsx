import { useNavigate } from 'react-router-dom'
import { useCart } from '@/features/cart/useCart'
import { usePlaceOrAppendMutation } from '@/features/orders/ordersApi'
import CartItemCard from '@/components/ui/CartItem'
import PriceSummary from '@/components/ui/PriceSummary'
import Button from '@/components/common/Button'
import styles from './Cart.module.css'

const CURRENCY = 'NPR'

export default function Cart() {
  const navigate = useNavigate()
  const { items, estimatedTotal, estimatedTax, isEmpty, updateQuantity, clearCart } = useCart()
  const [placeOrAppend, { isLoading, error }] = usePlaceOrAppendMutation()

  async function handlePlaceOrder() {
    if (isEmpty) return

    const requestBody = {
      items: items.map((item) => ({
        product_id: item.productId,
        variant_id: item.variantId ?? undefined,
        addon_ids: item.addonIds,
        quantity: item.quantity,
        special_instructions: item.specialInstructions || undefined,
      })),
    }

    try {
      await placeOrAppend(requestBody).unwrap()
      clearCart()
      navigate('/order-status', { replace: true })
    } catch {
      // error displayed below
    }
  }

  if (isEmpty) {
    return (
      <div className={styles.empty}>
        <span className={styles.emptyIcon}>🛒</span>
        <p>Your cart is empty</p>
        <Button variant="secondary" onClick={() => navigate('/menu')}>
          Browse Menu
        </Button>
      </div>
    )
  }

  const apiError = error as { data?: { detail?: string } } | undefined

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button onClick={() => navigate(-1)} className={styles.backBtn}>
          ← Back
        </button>
        <h1 className={styles.title}>Your Cart</h1>
      </header>

      <div className={styles.items}>
        {items.map((item) => (
          <CartItemCard
            key={item.key}
            item={item}
            currency={CURRENCY}
            onQuantityChange={updateQuantity}
          />
        ))}
      </div>

      <div className={styles.summary}>
        <PriceSummary
          mode="estimate"
          currency={CURRENCY}
          subtotal={estimatedTotal}
          tax={estimatedTax}
        />
      </div>

      {apiError?.data?.detail && (
        <p role="alert" className={styles.error}>
          {apiError.data.detail}
        </p>
      )}

      <div className={styles.footer}>
        <Button
          variant="secondary"
          onClick={() => navigate('/menu')}
          style={{ width: '100%', fontSize: '1rem', padding: '0.875rem' }}
        >
          + Add more Items
        </Button>
        <Button
          onClick={handlePlaceOrder}
          disabled={isLoading}
          style={{ width: '100%', fontSize: '1rem', padding: '0.875rem' }}
        >
          {isLoading ? 'Placing order…' : 'Place Order'}
        </Button>
      </div>
    </div>
  )
}
