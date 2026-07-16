import { z } from 'zod'

/** Mirrors backend LoginRequest (extra="forbid"). */
export const loginRequestSchema = z.object({
  email: z.string().email('Invalid email address').max(255),
  password: z.string().min(8, 'Password must be at least 8 characters').max(128),
  restaurant_slug: z.string().min(1, 'Restaurant slug is required').max(63).trim(),
  remember_me: z.boolean(),
})

export type LoginRequest = z.infer<typeof loginRequestSchema>

/** Mirrors backend TokenResponse. Role/user claims are decoded from the JWT payload. */
export const tokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.string(),
})

export type TokenResponse = z.infer<typeof tokenResponseSchema>

/** Mirrors backend ForgotPasswordRequest. */
export const forgotPasswordSchema = z.object({
  email: z.string().email('Invalid email address').max(255),
  restaurant_slug: z.string().min(1, 'Restaurant slug is required').max(63).trim(),
})

export type ForgotPasswordRequest = z.infer<typeof forgotPasswordSchema>

/** Mirrors backend ResetPasswordRequest (confirm handled in the component). */
export const resetPasswordSchema = z.object({
  token: z.string().min(1, 'Reset token is missing').max(512),
  new_password: z.string().min(8, 'Password must be at least 8 characters').max(128),
})

export type ResetPasswordRequest = z.infer<typeof resetPasswordSchema>

/** Mirrors backend MessageResponse. */
export const messageResponseSchema = z.object({
  message: z.string(),
})

export type MessageResponse = z.infer<typeof messageResponseSchema>
