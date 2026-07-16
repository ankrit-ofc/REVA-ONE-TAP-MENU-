import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery, setSessionToken } from '@/services/api'
import { clearStoredQrToken } from './qrStorage'
import { setSession, clearSession } from './sessionSlice'
import type { ScanRequest, SessionResponse } from '@/lib/schemas/session'
import type { AppDispatch } from '@/store/store'

export const sessionApi = createApi({
  reducerPath: 'sessionApi',
  baseQuery: axiosBaseQuery,
  endpoints: (builder) => ({
    scan: builder.mutation<SessionResponse, ScanRequest>({
      query: (body) => ({ method: 'POST', url: '/scan', data: body }),
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled
          setSessionToken(data.session_token)
          ;(dispatch as AppDispatch)(
            setSession({
              sessionToken: data.session_token,
              tableName: data.table_name,
              restaurantName: data.restaurant_name,
              expiresAt: data.expires_at,
            }),
          )
        } catch { /* handled by caller */ }
      },
    }),

    invalidateSession: builder.mutation<void, void>({
      query: () => ({ method: 'POST', url: '/session/invalidate' }),
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try { await queryFulfilled } catch { /* ignore */ }
        setSessionToken(null)
        clearStoredQrToken()
        ;(dispatch as AppDispatch)(clearSession())
      },
    }),

    // Notify-only: rings every waiter's dashboard for this table.
    callWaiter: builder.mutation<{ table_name: string }, void>({
      query: () => ({ method: 'POST', url: '/session/call-waiter' }),
    }),
  }),
})

export const {
  useScanMutation,
  useInvalidateSessionMutation,
  useCallWaiterMutation,
} = sessionApi
