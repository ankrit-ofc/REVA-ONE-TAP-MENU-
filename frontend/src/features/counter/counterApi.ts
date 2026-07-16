import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import {
  orderResponseSchema,
  type CounterOrderSummary,
  type OrderResponse,
} from '@/lib/schemas/order'
import {
  invoiceResponseSchema,
  receiptResponseSchema,
  type InvoiceResponse,
  type ReceiptResponse,
} from '@/lib/schemas/invoice'
import { printConfigSchema, type PrintConfig } from '@/lib/schemas/admin'

export interface GenerateInvoiceBody {
  order_id: string
  discount_type?: 'flat' | 'percent'
  discount_value?: number
}

export type CounterPayMethod = 'CASH' | 'CARD' | 'COUNTER_WALLET'

export const counterApi = createApi({
  reducerPath: 'counterApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['CounterInvoice', 'CounterOrders', 'CounterOpenOrders'],
  endpoints: (builder) => ({
    getCounterOrders: builder.query<CounterOrderSummary[], void>({
      query: () => ({ method: 'GET', url: '/counter/orders' }),
      providesTags: ['CounterOrders'],
    }),
    getCounterOpenOrders: builder.query<CounterOrderSummary[], void>({
      query: () => ({ method: 'GET', url: '/counter/open-orders' }),
      providesTags: ['CounterOpenOrders'],
    }),
    // Relay a manual kitchen-ticket print to the print station. No cache change —
    // printing happens on the station via WebSocket, not in this response.
    printKot: builder.mutation<void, { orderId: string }>({
      query: ({ orderId }) => ({ method: 'POST', url: `/counter/orders/${orderId}/print-kot` }),
    }),
    markMealFinished: builder.mutation<OrderResponse, string>({
      query: (orderId) => ({
        method: 'POST',
        url: `/counter/orders/${orderId}/meal-finished`,
      }),
      transformResponse: parseWith(orderResponseSchema),
      // Moving a table to billing removes it from open-orders and adds it to
      // the MEAL_FINISHED queue — refresh both.
      invalidatesTags: ['CounterOpenOrders', 'CounterOrders'],
    }),
    reopenCounterOrder: builder.mutation<OrderResponse, { orderId: string; reason: string }>({
      query: ({ orderId, reason }) => ({
        method: 'POST',
        url: `/counter/orders/${orderId}/reopen`,
        data: { reason },
      }),
      transformResponse: parseWith(orderResponseSchema),
      // Reopened order leaves the MEAL_FINISHED queue and returns to Open Tables.
      invalidatesTags: ['CounterOrders', 'CounterOpenOrders'],
    }),
    startBilling: builder.mutation<OrderResponse, string>({
      query: (orderId) => ({ method: 'POST', url: `/counter/orders/${orderId}/start-billing` }),
      transformResponse: parseWith(orderResponseSchema),
      invalidatesTags: ['CounterOpenOrders'],
    }),
    closeUnpaid: builder.mutation<OrderResponse, { orderId: string; reason: string }>({
      query: ({ orderId, reason }) => ({
        method: 'POST',
        url: `/counter/orders/${orderId}/close-unpaid`,
        data: { reason },
      }),
      transformResponse: parseWith(orderResponseSchema),
      invalidatesTags: ['CounterOpenOrders', 'CounterOrders'],
    }),
    // One-tap: bill an OPEN, bill-requested order with the chosen method, then
    // close it and clear the table. Returns the PAID invoice. Idempotency-Key
    // makes retries safe. The order leaves both queues on success.
    quickBill: builder.mutation<
      InvoiceResponse,
      { orderId: string; method: CounterPayMethod; idempotencyKey: string }
    >({
      query: ({ orderId, method, idempotencyKey }) => ({
        method: 'POST',
        url: `/counter/orders/${orderId}/quick-bill`,
        data: { method },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
      transformResponse: parseWith(invoiceResponseSchema),
      invalidatesTags: ['CounterOpenOrders', 'CounterOrders'],
    }),
    generateInvoice: builder.mutation<InvoiceResponse, GenerateInvoiceBody>({
      query: (body) => ({ method: 'POST', url: '/invoices', data: body }),
      transformResponse: parseWith(invoiceResponseSchema),
      invalidatesTags: ['CounterInvoice'],
    }),
    getInvoice: builder.query<InvoiceResponse, string>({
      query: (id) => ({ method: 'GET', url: `/invoices/${id}` }),
      transformResponse: parseWith(invoiceResponseSchema),
      providesTags: ['CounterInvoice'],
    }),
    getReceipt: builder.query<ReceiptResponse, string>({
      query: (id) => ({ method: 'GET', url: `/invoices/${id}/receipt` }),
      transformResponse: parseWith(receiptResponseSchema),
    }),
    getPrintConfig: builder.query<PrintConfig, void>({
      query: () => ({ method: 'GET', url: '/counter/print-config' }),
      transformResponse: parseWith(printConfigSchema),
    }),
    payInvoice: builder.mutation<
      InvoiceResponse,
      { invoiceId: string; method: CounterPayMethod; idempotencyKey: string }
    >({
      query: ({ invoiceId, method, idempotencyKey }) => ({
        method: 'POST',
        url: `/invoices/${invoiceId}/pay`,
        data: { method },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
      transformResponse: parseWith(invoiceResponseSchema),
      // Payment closes the order — drop it from the MEAL_FINISHED queue immediately.
      invalidatesTags: ['CounterInvoice', 'CounterOrders'],
    }),
    manualOverride: builder.mutation<
      InvoiceResponse,
      { invoiceId: string; reason: string }
    >({
      query: ({ invoiceId, reason }) => ({
        method: 'POST',
        url: `/invoices/${invoiceId}/override`,
        data: { reason },
      }),
      transformResponse: parseWith(invoiceResponseSchema),
      invalidatesTags: ['CounterInvoice', 'CounterOrders'],
    }),
  }),
})

export const {
  useGetCounterOrdersQuery,
  useGetCounterOpenOrdersQuery,
  usePrintKotMutation,
  useMarkMealFinishedMutation,
  useReopenCounterOrderMutation,
  useStartBillingMutation,
  useCloseUnpaidMutation,
  useQuickBillMutation,
  useGenerateInvoiceMutation,
  useGetInvoiceQuery,
  useLazyGetReceiptQuery,
  useGetPrintConfigQuery,
  usePayInvoiceMutation,
  useManualOverrideMutation,
} = counterApi
