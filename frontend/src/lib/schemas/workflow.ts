import { z } from 'zod'
import { orderItemStatusSchema, orderItemAddonResponseSchema } from './order'

export const queueItemResponseSchema = z.object({
  id: z.string().uuid(),
  order_id: z.string().uuid(),
  order_number: z.number().int(),
  table_name: z.string().nullable().optional(),
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

export type QueueItemResponse = z.infer<typeof queueItemResponseSchema>
