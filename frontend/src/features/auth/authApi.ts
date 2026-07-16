import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery, setAccessToken } from '@/services/api'
import { setCredentials, clearAuth } from './authSlice'
import { decodeJwtPayload } from '@/lib/jwt'
import type {
  ForgotPasswordRequest,
  LoginRequest,
  MessageResponse,
  ResetPasswordRequest,
  TokenResponse,
} from '@/lib/schemas/auth'
import type { Role } from '@/types'
import type { AppDispatch } from '@/store/store'

export interface MeResponse {
  email: string
  role: Role
  restaurant_id: string
  restaurant_name: string | null
}

export const authApi = createApi({
  reducerPath: 'authApi',
  baseQuery: axiosBaseQuery,
  endpoints: (builder) => ({
    getMe: builder.query<MeResponse, void>({
      query: () => ({ method: 'GET', url: '/auth/me' }),
    }),
    login: builder.mutation<TokenResponse, LoginRequest>({
      query: (body) => ({ method: 'POST', url: '/auth/login', data: body }),
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled
          _applyToken(data.access_token, dispatch as AppDispatch)
        } catch {
          // login failure handled by component via unwrap()
        }
      },
    }),

    logout: builder.mutation<{ status: string }, void>({
      query: () => ({ method: 'POST', url: '/auth/logout' }),
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        // Clear state regardless of whether the server call succeeds.
        try { await queryFulfilled } catch { /* ignore */ }
        setAccessToken(null)
        dispatch(clearAuth())
      },
    }),

    forgotPassword: builder.mutation<MessageResponse, ForgotPasswordRequest>({
      query: (body) => ({ method: 'POST', url: '/auth/forgot-password', data: body }),
    }),

    resetPassword: builder.mutation<MessageResponse, ResetPasswordRequest>({
      query: (body) => ({ method: 'POST', url: '/auth/reset-password', data: body }),
    }),
  }),
})

/** Apply a fresh access token: decode claims, persist in memory, update store. */
export function _applyToken(accessToken: string, dispatch: AppDispatch): void {
  setAccessToken(accessToken)
  const payload = decodeJwtPayload(accessToken)
  dispatch(
    setCredentials({
      userId: String(payload['sub'] ?? ''),
      restaurantId: String(payload['restaurant_id'] ?? ''),
      role: String(payload['role'] ?? '') as Role,
    }),
  )
}

export const {
  useGetMeQuery,
  useLoginMutation,
  useLogoutMutation,
  useForgotPasswordMutation,
  useResetPasswordMutation,
} = authApi
