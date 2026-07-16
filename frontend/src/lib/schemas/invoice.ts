import { z } from 'zod'

export const invoiceStatusSchema = z.enum([
  'DRAFT', 'PENDING_PAYMENT', 'PAID', 'FAILED', 'VOID', 'REFUNDED',
])

export const paymentMethodSchema = z.enum([
  'CASH', 'CARD', 'COUNTER_WALLET', 'QR_GATEWAY', 'MANUAL_OVERRIDE',
])

export const invoiceResponseSchema = z.object({
  id: z.string().uuid(),
  order_id: z.string().uuid(),
  invoice_number: z.string(),
  status: invoiceStatusSchema,
  payment_method: paymentMethodSchema.nullable(),
  subtotal: z.coerce.number(),
  discount: z.coerce.number(),
  tax_total: z.coerce.number(),
  total: z.coerce.number(),
  gateway_transaction_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const gatewayIntentRequestSchema = z.object({
  gateway: z.enum(['esewa', 'khalti', 'fonepay']),
})

// Itemized printable receipt (thermal printing).
export const receiptAddonSchema = z.object({
  addon_name: z.string(),
  addon_price: z.coerce.number(),
})

export const receiptLineSchema = z.object({
  product_name: z.string(),
  variant_name: z.string().nullable(),
  quantity: z.number(),
  unit_price: z.coerce.number(),
  line_total: z.coerce.number(),
  special_instructions: z.string().nullable(),
  addons: z.array(receiptAddonSchema),
})

export const receiptResponseSchema = z.object({
  invoice_number: z.string(),
  status: invoiceStatusSchema,
  payment_method: paymentMethodSchema.nullable(),
  currency: z.string(),
  restaurant_name: z.string(),
  table_name: z.string(),
  order_number: z.number(),
  created_at: z.string(),
  items: z.array(receiptLineSchema),
  subtotal: z.coerce.number(),
  discount: z.coerce.number(),
  tax_total: z.coerce.number(),
  total: z.coerce.number(),
})

export type InvoiceStatus = z.infer<typeof invoiceStatusSchema>
export type PaymentMethod = z.infer<typeof paymentMethodSchema>
export type InvoiceResponse = z.infer<typeof invoiceResponseSchema>
export type GatewayIntentRequest = z.infer<typeof gatewayIntentRequestSchema>
export type ReceiptResponse = z.infer<typeof receiptResponseSchema>
