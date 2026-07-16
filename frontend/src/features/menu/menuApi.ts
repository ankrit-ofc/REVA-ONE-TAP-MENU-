import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import { menuResponseSchema, type MenuResponse } from '@/lib/schemas/menu'

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
    }),
  }),
})

export const { useGetMenuQuery } = menuApi
