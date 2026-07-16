import { useSelector, useDispatch } from 'react-redux'
import type { RootState } from '@/store/store'
import {
  addItem,
  removeItem,
  updateQuantity,
  clearCart,
  makeCartKey,
  type CartItem,
} from './cartSlice'

export function useCart() {
  const items = useSelector((state: RootState) => state.cart.items)
  const dispatch = useDispatch()

  const totalItems = items.reduce((sum, i) => sum + i.quantity, 0)

  const estimatedTotal = items.reduce((sum, i) => {
    const linePrice = (i.unitPrice + i.addonPriceTotal) * i.quantity
    return sum + linePrice
  }, 0)

  const estimatedTax = items.reduce((sum, i) => {
    const linePrice = (i.unitPrice + i.addonPriceTotal) * i.quantity
    return sum + linePrice * (i.taxRate / 100)
  }, 0)

  return {
    items,
    totalItems,
    estimatedTotal,
    estimatedTax,
    isEmpty: items.length === 0,
    addItem: (item: CartItem) => dispatch(addItem(item)),
    removeItem: (key: string) => dispatch(removeItem(key)),
    updateQuantity: (key: string, quantity: number) =>
      dispatch(updateQuantity({ key, quantity })),
    clearCart: () => dispatch(clearCart()),
    makeCartKey,
  }
}
