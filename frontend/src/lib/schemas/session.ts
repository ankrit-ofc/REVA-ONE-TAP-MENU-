import { z } from 'zod'

/** Mirrors backend ScanRequest. Coordinates are sent only on the geofence retry. */
export const scanRequestSchema = z.object({
  qr_token: z.string().min(1, 'QR token is required'),
  latitude: z.number().optional(),
  longitude: z.number().optional(),
  accuracy: z.number().optional(),
})

export type ScanRequest = z.infer<typeof scanRequestSchema>

/** Mirrors backend SessionResponse. Flags are COMPUTED server-side. Optional for
 * backward compat with older backends — treat missing as enabled. */
export const sessionResponseSchema = z.object({
  session_token: z.string().min(1),
  table_name: z.string(),
  restaurant_name: z.string(),
  expires_at: z.string().datetime({ offset: true }),
  order_enabled: z.boolean().optional(),
  call_waiter_enabled: z.boolean().optional(),
  ar_enabled: z.boolean().optional(),
  qr_pay_enabled: z.boolean().optional(),
})

export type SessionResponse = z.infer<typeof sessionResponseSchema>
