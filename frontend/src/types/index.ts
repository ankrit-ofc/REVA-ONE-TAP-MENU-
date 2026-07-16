export type Role = 'SUPERADMIN' | 'ADMIN' | 'KITCHEN' | 'WAITER' | 'COUNTER' | 'COUNTER_DISPLAY'

export interface AuthUser {
  userId: string
  restaurantId: string
  role: Role
}

/** Slim event envelope — each event has at minimum a `type` discriminator. */
export interface RealtimeEvent {
  type: string
  restaurant_id: string
  [key: string]: unknown
}
