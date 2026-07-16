import type { OrderItemResponse } from '@/lib/schemas/order'

/**
 * Client-side estimates from the item snapshots — the same maths the Cart uses.
 * The authoritative totals come from the staff-generated invoice (server-side);
 * these are shown only as a guide before the invoice exists.
 */

/** Pre-tax line cost for one item: (unit + addons) × quantity. */
export function estimateItemLine(item: OrderItemResponse): number {
  const addonTotal = item.addons.reduce((s, a) => s + a.addon_price, 0)
  return (item.unit_price + addonTotal) * item.quantity
}

/** Estimated grand total across all items, including per-item tax. */
export function estimateOrderTotal(items: OrderItemResponse[]): number {
  return items.reduce((sum, item) => {
    const line = estimateItemLine(item)
    const tax = line * (item.tax_rate / 100)
    return sum + line + tax
  }, 0)
}
