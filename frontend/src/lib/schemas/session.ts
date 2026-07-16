import { z } from 'zod'

/** Mirrors backend ScanRequest. Coordinates are sent only on the geofence retry. */
export const scanRequestSchema = z.object({
  qr_token: z.string().min(1, 'QR token is required'),
  latitude: z.number().optional(),
  longitude: z.number().optional(),
  accuracy: z.number().optional(),
})

export type ScanRequest = z.infer<typeof scanRequestSchema>

/** Mirrors backend SessionResponse. */
export const sessionResponseSchema = z.object({
  session_token: z.string().min(1),
  table_name: z.string(),
  restaurant_name: z.string(),
  expires_at: z.string().datetime({ offset: true }),
})

export type SessionResponse = z.infer<typeof sessionResponseSchema>
