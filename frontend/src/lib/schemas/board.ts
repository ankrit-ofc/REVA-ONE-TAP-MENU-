import { z } from 'zod'
import { orderItemStatusSchema } from './order'

/** A single row on the passive counter display board. */
export const displayBoardItemSchema = z.object({
  id: z.string().uuid(),
  order_number: z.number().int(),
  table_name: z.string(),
  product_name: z.string(),
  variant_name: z.string().nullable(),
  quantity: z.number().int(),
  status: orderItemStatusSchema, // NEW / PREPARING / READY / SERVED
  ready_at: z.string().nullable(),
  served_at: z.string().nullable(),
})

export type DisplayBoardItem = z.infer<typeof displayBoardItemSchema>
