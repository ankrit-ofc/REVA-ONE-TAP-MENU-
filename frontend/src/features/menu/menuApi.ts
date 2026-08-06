import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import { menuResponseSchema, type MenuResponse } from '@/lib/schemas/menu'
import { setFeatureFlags } from '@/features/session/sessionSlice'
import type { AppDispatch } from '@/store/store'

export const menuApi = createApi({
  reducerPath: 'menuApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['Menu'],
  endpoints: (builder) => ({
    getMenu: builder.query<MenuResponse, void>({
      query: () => ({ method: 'GET', url: '/menu' }),
      // Coerce Decimal-as-string money fields (base_price, tax_rate, …).
      transformResponse: parseWith(menuResponseSchema),
      providesTags: ['Menu'],
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled
          ;(dispatch as AppDispatch)(
            setFeatureFlags({
              orderEnabled: data.order_enabled,
              callWaiterEnabled: data.call_waiter_enabled,
              arEnabled: data.ar_enabled,
              qrPaymentEnabled: data.qr_pay_enabled,
              menuTemplate: data.menu_template,
              menuAccentColor: data.menu_accent_color,
            }),
          )
        } catch {
          /* handled by caller */
        }
      },
    }),
  }),
})

export const { useGetMenuQuery } = menuApi
