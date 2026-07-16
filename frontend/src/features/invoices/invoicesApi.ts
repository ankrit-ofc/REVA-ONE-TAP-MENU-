import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import {
  invoiceResponseSchema,
  type InvoiceResponse,
  type GatewayIntentRequest,
} from '@/lib/schemas/invoice'

export const invoicesApi = createApi({
  reducerPath: 'invoicesApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['MyInvoice'],
  endpoints: (builder) => ({
    getMyOrderInvoice: builder.query<InvoiceResponse | null, void>({
      query: () => ({ method: 'GET', url: '/invoices/my-order' }),
      // /invoices/my-order returns null until an invoice exists; coerce the
      // Decimal-as-string money fields (subtotal, total, …) otherwise.
      transformResponse: parseWith(invoiceResponseSchema.nullable()),
      providesTags: ['MyInvoice'],
    }),

    createGatewayIntent: builder.mutation<
      Record<string, unknown>,
      { invoiceId: string; body: GatewayIntentRequest }
    >({
      query: ({ invoiceId, body }) => ({
        method: 'POST',
        url: `/invoices/${invoiceId}/intent`,
        data: body,
      }),
    }),
  }),
})

export const { useGetMyOrderInvoiceQuery, useCreateGatewayIntentMutation } =
  invoicesApi
