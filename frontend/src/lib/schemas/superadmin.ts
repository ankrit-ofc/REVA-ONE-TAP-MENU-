import { z } from 'zod'

const adminInfoSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
})

export const restaurantResponseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  admins: z.array(adminInfoSchema).default([]),
})

export const restaurantCreateResponseSchema = z.object({
  restaurant: restaurantResponseSchema,
  admin_email: z.string(),
})

export type RestaurantResponse = z.infer<typeof restaurantResponseSchema>
export type RestaurantCreateResponse = z.infer<typeof restaurantCreateResponseSchema>
