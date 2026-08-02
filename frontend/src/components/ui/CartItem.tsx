import { useState } from 'react'
import type { CartItem as CartItemType } from '@/features/cart/cartSlice'
import { formatPrice } from '@/lib/currency'
import ItemNoteEditor from './ItemNoteEditor'
import styles from './CartItem.module.css'

interface Props {
  item: CartItemType
  currency: string
  onQuantityChange: (key: string, qty: number) => void
  onNoteChange: (key: string, note: string) => void
}

export default function CartItem({ item, currency, onQuantityChange, onNoteChange }: Props) {
  const [isEditingNote, setIsEditingNote] = useState(false)
  const linePrice = (item.unitPrice + item.addonPriceTotal) * item.quantity

  return (
    <div className={styles.item}>
      <div className={styles.info}>
        <div className={styles.name}>{item.productName}</div>
        {item.variantName && (
          <div className={styles.variant}>{item.variantName}</div>
        )}
        {item.addonNames.length > 0 && (
          <div className={styles.addons}>+ {item.addonNames.join(', ')}</div>
        )}
        {item.specialInstructions && !isEditingNote && (
          <div className={styles.instructions}>
            &ldquo;{item.specialInstructions}&rdquo;
          </div>
        )}
        {!isEditingNote && (
          <button
            type="button"
            className={styles.noteToggle}
            onClick={() => setIsEditingNote(true)}
          >
            {item.specialInstructions ? 'Edit note' : '+ Add note'}
          </button>
        )}
        {isEditingNote && (
          <ItemNoteEditor
            value={item.specialInstructions}
            onCancel={() => setIsEditingNote(false)}
            onSave={(note) => {
              onNoteChange(item.key, note)
              setIsEditingNote(false)
            }}
          />
        )}
      </div>

      <div className={styles.right}>
        <span className={styles.price}>
          {formatPrice(linePrice, currency)}
        </span>
        <div className={styles.qty}>
          <button
            className={styles.qtyBtn}
            onClick={() => onQuantityChange(item.key, item.quantity - 1)}
            aria-label="Decrease quantity"
          >
            −
          </button>
          <span className={styles.qtyNum}>{item.quantity}</span>
          <button
            className={styles.qtyBtn}
            onClick={() => onQuantityChange(item.key, item.quantity + 1)}
            aria-label="Increase quantity"
          >
            +
          </button>
        </div>
      </div>
    </div>
  )
}
