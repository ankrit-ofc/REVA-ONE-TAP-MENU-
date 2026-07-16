import { z } from 'zod'
import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import { queueItemResponseSchema, type QueueItemResponse } from '@/lib/schemas/workflow'
import { orderItemResponseSchema, type OrderItemResponse } from '@/lib/schemas/order'

export const kitchenApi = createApi({
  reducerPath: 'kitchenApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['KitchenQueue'],
  endpoints: (builder) => ({
    getKitchenQueue: builder.query<QueueItemResponse[], void>({
      query: () => ({ method: 'GET', url: '/kitchen/queue' }),
      // Coerce Decimal-as-string money fields (unit_price, tax_rate, …).
      transformResponse: parseWith(z.array(queueItemResponseSchema)),
      providesTags: ['KitchenQueue'],
    }),
    markPreparing: builder.mutation<OrderItemResponse, string>({
      query: (itemId) => ({ method: 'POST', url: `/kitchen/items/${itemId}/preparing` }),
      transformResponse: parseWith(orderItemResponseSchema),
      invalidatesTags: ['KitchenQueue'],
    }),
    markReady: builder.mutation<OrderItemResponse, string>({
      query: (itemId) => ({ method: 'POST', url: `/kitchen/items/${itemId}/ready` }),
      transformResponse: parseWith(orderItemResponseSchema),
      invalidatesTags: ['KitchenQueue'],
    }),
  }),
})

export const {
  useGetKitchenQueueQuery,
  useMarkPreparingMutation,
  useMarkReadyMutation,
} = kitchenApi
