import { z } from 'zod'

const adminInfoSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
})

export const restaurantPlanSchema = z.enum(['basic', 'starter', 'custom'])
export type RestaurantPlan = z.infer<typeof restaurantPlanSchema>

/** Defaults written when a plan is assigned (mirrors backend apply_plan_preset). */
export function planPreset(plan: RestaurantPlan): {
  order_enabled: boolean
  call_waiter_enabled: boolean
  ar_enabled: boolean
  qr_pay_enabled: boolean
} {
  if (plan === 'basic') {
    return {
      order_enabled: false,
      call_waiter_enabled: false,
      ar_enabled: false,
      qr_pay_enabled: false,
    }
  }
  if (plan === 'starter') {
    return {
      order_enabled: true,
      call_waiter_enabled: true,
      ar_enabled: false,
      qr_pay_enabled: false,
    }
  }
  return {
    order_enabled: true,
    call_waiter_enabled: true,
    ar_enabled: true,
    qr_pay_enabled: true,
  }
}

export const restaurantResponseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  is_active: z.boolean(),
  plan: restaurantPlanSchema,
  order_enabled: z.boolean(),
  call_waiter_enabled: z.boolean(),
  ar_enabled: z.boolean(),
  qr_pay_enabled: z.boolean(),
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
