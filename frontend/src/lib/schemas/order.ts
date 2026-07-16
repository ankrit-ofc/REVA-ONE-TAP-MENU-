import { z } from 'zod'

export const orderItemStatusSchema = z.enum([
  'PENDING_APPROVAL', 'NEW', 'PREPARING', 'READY', 'SERVED', 'CANCELLED',
])

export const orderStatusSchema = z.enum(['OPEN', 'MEAL_FINISHED', 'CLOSED'])

export const orderItemAddonResponseSchema = z.object({
  id: z.string().uuid(),
  addon_name: z.string(),
  addon_price: z.coerce.number(),
})

export const orderItemResponseSchema = z.object({
  id: z.string().uuid(),
  product_name: z.string(),
  variant_name: z.string().nullable(),
  unit_price: z.coerce.number(),
  tax_rate: z.coerce.number(),
  quantity: z.number().int(),
  special_instructions: z.string().nullable(),
  status: orderItemStatusSchema,
  preparing_at: z.string().nullable(),
  ready_at: z.string().nullable(),
  served_at: z.string().nullable(),
  addons: z.array(orderItemAddonResponseSchema),
})

export const orderResponseSchema = z.object({
  id: z.string().uuid(),
  order_number: z.number().int(),
  status: orderStatusSchema,
  created_at: z.string(),
  updated_at: z.string(),
  items: z.array(orderItemResponseSchema),
})

/** Request shape — only what the backend accepts; no price/name/table_id. */
export const orderItemCreateSchema = z.object({
  product_id: z.string().uuid(),
  variant_id: z.string().uuid().nullable().optional(),
  addon_ids: z.array(z.string().uuid()).default([]),
  quantity: z.number().int().min(1).max(99),
  special_instructions: z.string().max(500).nullable().optional(),
})

export const placeOrderRequestSchema = z.object({
  items: z.array(orderItemCreateSchema).min(1).max(50),
})

export const counterOrderSummarySchema = z.object({
  id: z.string().uuid(),
  order_number: z.number().int(),
  status: orderStatusSchema,
  table_name: z.string(),
  item_count: z.number().int(),
  pending_item_count: z.number().int(),
  bill_requested: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

export type OrderItemStatus = z.infer<typeof orderItemStatusSchema>
export type OrderStatus = z.infer<typeof orderStatusSchema>
export type OrderItemAddonResponse = z.infer<typeof orderItemAddonResponseSchema>
export type OrderItemResponse = z.infer<typeof orderItemResponseSchema>
export type OrderResponse = z.infer<typeof orderResponseSchema>
export type OrderItemCreate = z.infer<typeof orderItemCreateSchema>
export type PlaceOrderRequest = z.infer<typeof placeOrderRequestSchema>
export type CounterOrderSummary = z.infer<typeof counterOrderSummarySchema>
