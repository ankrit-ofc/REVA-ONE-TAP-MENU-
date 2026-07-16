import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import {
  orderResponseSchema,
  type OrderResponse,
  type PlaceOrderRequest,
} from '@/lib/schemas/order'

export const ordersApi = createApi({
  reducerPath: 'ordersApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['CurrentOrder'],
  endpoints: (builder) => ({
    placeOrAppend: builder.mutation<OrderResponse, PlaceOrderRequest>({
      query: (body) => ({ method: 'POST', url: '/orders/items', data: body }),
      // Coerce Decimal-as-string money fields (unit_price, tax_rate, …).
      transformResponse: parseWith(orderResponseSchema),
      invalidatesTags: ['CurrentOrder'],
    }),

    getCurrentOrder: builder.query<OrderResponse, void>({
      query: () => ({ method: 'GET', url: '/orders/current' }),
      transformResponse: parseWith(orderResponseSchema),
      providesTags: ['CurrentOrder'],
    }),

    // Notify-only: signals staff to move this table to billing. No state change.
    requestBill: builder.mutation<OrderResponse, void>({
      query: () => ({ method: 'POST', url: '/orders/request-bill' }),
      transformResponse: parseWith(orderResponseSchema),
    }),
  }),
})

export const {
  usePlaceOrAppendMutation,
  useGetCurrentOrderQuery,
  useRequestBillMutation,
} = ordersApi
