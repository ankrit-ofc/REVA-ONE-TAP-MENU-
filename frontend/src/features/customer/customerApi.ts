import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'

export interface CustomerContactRequest {
  email: string
  name?: string
  phone?: string
}

export interface CustomerContactAck {
  status: string
}

export const customerApi = createApi({
  reducerPath: 'customerApi',
  baseQuery: axiosBaseQuery,
  endpoints: (builder) => ({
    /**
     * Submit contact details for an emailed receipt.
     *
     * `sessionToken` is an explicit override for the post-payment entry point:
     * paying invalidates the table session, and endCustomerSession clears the
     * in-memory token, so by the time the "payment received" screen renders the
     * axios interceptor has nothing to attach. The paid screen keeps the token
     * it saw and passes it here. The backend accepts it inside a short grace
     * window (deps.get_contact_capture_session) for this write-only endpoint.
     */
    submitContact: builder.mutation<
      CustomerContactAck,
      { body: CustomerContactRequest; sessionToken?: string | null }
    >({
      query: ({ body, sessionToken }) => ({
        method: 'POST',
        url: '/session/contact',
        data: body,
        ...(sessionToken ? { headers: { 'X-Session-Token': sessionToken } } : {}),
      }),
    }),
  }),
})

export const { useSubmitContactMutation } = customerApi
