import { useDispatch } from 'react-redux'
import {
  useGetMyOrderInvoiceQuery,
  useCreateGatewayIntentMutation,
  invoicesApi,
} from './invoicesApi'
import type { AppDispatch } from '@/store/store'

export function useInvoices() {
  const dispatch = useDispatch<AppDispatch>()

  const invoiceQuery = useGetMyOrderInvoiceQuery(undefined, {
    pollingInterval: 15_000,
  })

  const [createIntent, intentState] = useCreateGatewayIntentMutation()

  function invalidateMyInvoice() {
    dispatch(invoicesApi.util.invalidateTags(['MyInvoice']))
  }

  return {
    invoice: invoiceQuery.data ?? null,
    isLoadingInvoice: invoiceQuery.isLoading,
    invoiceError: invoiceQuery.error,
    createIntent,
    isCreatingIntent: intentState.isLoading,
    intentData: intentState.data ?? null,
    invalidateMyInvoice,
  }
}
