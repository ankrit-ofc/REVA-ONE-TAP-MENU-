/**
 * Render KOT (kitchen) and bill receipts to ESC/POS bytes for an 80 mm printer.
 * The KOT is itemized with per-line prices + subtotal/tax/total for THIS order (money
 * is computed server-side and rides the order.created event as strings); the bill uses
 * authoritative invoice totals.
 */
import { EscPos } from '@/lib/escpos/encoder'
import type { ReceiptResponse } from '@/lib/schemas/invoice'

type Money = string | number | null | undefined

export interface KotItem {
  product_name: string
  variant_name: string | null
  quantity: number
  special_instructions: string | null
  addons: string[]
  line_total?: Money
}

export interface KotData {
  restaurantName: string
  orderNumber: number
  tableName: string
  items: KotItem[]
  currency?: string
  subtotal?: Money
  taxTotal?: Money
  total?: Money
}

export function buildKotBytes(d: KotData): Uint8Array {
  const cur = d.currency || 'Rs'
  const money = (n: Money): string => {
    const v = Number(n)
    return Number.isFinite(v) ? `${cur} ${v.toFixed(2)}` : ''
  }
  // Older events carried no prices — fall back to the item-only layout then.
  const priced = d.total != null || d.items.some((it) => it.line_total != null)

  const p = new EscPos().init()
  p.align('center').bold(true).size('double').line(d.restaurantName || 'Kitchen')
  p.size('normal').line('KITCHEN ORDER (KOT)').bold(false)
  p.align('left').divider()
  p.twoCol(`Order #${d.orderNumber}`, d.tableName ? `Table ${d.tableName}` : '')
  p.line(new Date().toLocaleString())
  p.divider()

  for (const it of d.items) {
    const name = it.variant_name ? `${it.product_name} (${it.variant_name})` : it.product_name
    const left = `${it.quantity} x ${name}`
    if (priced && it.line_total != null) {
      p.bold(true).twoCol(left, money(it.line_total)).bold(false)
    } else {
      p.bold(true).line(left).bold(false)
    }
    for (const a of it.addons) p.line(`   + ${a}`)
    if (it.special_instructions) p.bold(true).line(`   ! ${it.special_instructions}`).bold(false)
  }

  p.divider()
  if (priced) {
    if (d.subtotal != null) p.twoCol('Subtotal', money(d.subtotal))
    if (d.taxTotal != null) p.twoCol('Tax', money(d.taxTotal))
    p.divider()
    // TOTAL big & centered (double-size halves the columns, so avoid twoCol).
    p.align('center').bold(true).size('double').line(`TOTAL  ${money(d.total)}`)
    p.size('normal').bold(false).align('left')
  }
  return p.cut().build()
}

export function buildBillBytes(r: ReceiptResponse, copyLabel: string): Uint8Array {
  const money = (n: number) => `${r.currency} ${n.toFixed(2)}`
  const p = new EscPos().init()
  p.align('center').bold(true).size('double').line(r.restaurant_name || 'Receipt')
  p.size('normal').line('TAX INVOICE').bold(false)
  p.line(r.invoice_number)
  p.align('left').divider()
  p.twoCol(r.table_name ? `Table ${r.table_name}` : '', `Order #${r.order_number}`)
  p.line(new Date(r.created_at).toLocaleString())
  p.divider()
  for (const it of r.items) {
    const name = it.variant_name ? `${it.product_name} (${it.variant_name})` : it.product_name
    p.twoCol(`${it.quantity} x ${name}`, money(it.line_total))
    for (const a of it.addons) p.twoCol(`   + ${a.addon_name}`, money(a.addon_price))
    if (it.special_instructions) p.line(`   ! ${it.special_instructions}`)
  }
  p.divider()
  p.twoCol('Subtotal', money(r.subtotal))
  if (r.discount > 0) p.twoCol('Discount', `- ${money(r.discount)}`)
  p.twoCol('Tax', money(r.tax_total))
  p.divider()
  // TOTAL big & centered (double-size halves the column count, so avoid twoCol).
  p.align('center').bold(true).size('double').line(`TOTAL  ${money(r.total)}`)
  p.size('normal').bold(false).align('left')
  if (r.payment_method) p.line(`Paid: ${r.payment_method}`)
  p.align('center').feed(1).bold(true).line(copyLabel).bold(false)
  return p.cut().build()
}

/** A tiny test page to confirm a freshly-paired printer responds. */
export function buildTestBytes(label: string): Uint8Array {
  const p = new EscPos().init()
  p.align('center').bold(true).size('double').line('TEST PRINT')
  p.size('normal').bold(false).line(label)
  p.line(new Date().toLocaleString())
  p.line('If you can read this, the printer works.')
  return p.cut().build()
}
