/**
 * Client-side cart draft.
 *
 * Prices stored here are ESTIMATES only (from the menu at browse time).
 * The server snapshots the authoritative price at order placement.
 * Never treat these values as financial truth — always show a label like
 * "Estimated total" and confirm with the server response.
 */
import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export interface CartItem {
  key: string // stable key: productId + variantId + sorted addonIds
  productId: string
  productName: string
  variantId: string | null
  variantName: string | null
  addonIds: string[]
  addonNames: string[]
  addonPriceTotal: number
  quantity: number
  specialInstructions: string
  unitPrice: number // estimate from menu
  taxRate: number
}

interface CartState {
  items: CartItem[]
}

const initialState: CartState = { items: [] }

export function makeCartKey(
  productId: string,
  variantId: string | null,
  addonIds: string[],
): string {
  return [productId, variantId ?? '', ...[...addonIds].sort()].join('|')
}

const cartSlice = createSlice({
  name: 'cart',
  initialState,
  reducers: {
    addItem(state, action: PayloadAction<CartItem>) {
      const idx = state.items.findIndex((i) => i.key === action.payload.key)
      if (idx >= 0) {
        state.items[idx].quantity += action.payload.quantity
      } else {
        state.items.push(action.payload)
      }
    },

    removeItem(state, action: PayloadAction<string>) {
      state.items = state.items.filter((i) => i.key !== action.payload)
    },

    updateQuantity(
      state,
      action: PayloadAction<{ key: string; quantity: number }>,
    ) {
      const item = state.items.find((i) => i.key === action.payload.key)
      if (item) {
        if (action.payload.quantity <= 0) {
          state.items = state.items.filter((i) => i.key !== action.payload.key)
        } else {
          item.quantity = action.payload.quantity
        }
      }
    },

    clearCart(state) {
      state.items = []
    },
  },
})

export const { addItem, removeItem, updateQuantity, clearCart } = cartSlice.actions
export default cartSlice.reducer
