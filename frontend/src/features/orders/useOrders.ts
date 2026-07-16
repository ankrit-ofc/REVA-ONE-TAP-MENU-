import { useDispatch } from 'react-redux'
import {
  usePlaceOrAppendMutation,
  useGetCurrentOrderQuery,
  ordersApi,
} from './ordersApi'
import type { AppDispatch } from '@/store/store'

export function useOrders() {
  const dispatch = useDispatch<AppDispatch>()
  const [placeOrAppend, placeState] = usePlaceOrAppendMutation()
  const currentOrderQuery = useGetCurrentOrderQuery(undefined, {
    // Poll every 30 s as fallback; WS invalidations are the primary update path.
    pollingInterval: 30_000,
  })

  function invalidateCurrentOrder() {
    dispatch(ordersApi.util.invalidateTags(['CurrentOrder']))
  }

  return {
    currentOrder: currentOrderQuery.data,
    isLoadingOrder: currentOrderQuery.isLoading,
    orderError: currentOrderQuery.error,
    placeOrAppend,
    isPlacing: placeState.isLoading,
    placeError: placeState.error,
    invalidateCurrentOrder,
  }
}
