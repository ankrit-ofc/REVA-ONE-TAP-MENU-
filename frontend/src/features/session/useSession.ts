import { useSelector } from 'react-redux'
import type { RootState } from '@/store/store'
import { useScanMutation, useInvalidateSessionMutation } from './sessionApi'

export function useSession() {
  const session = useSelector((state: RootState) => state.session)
  const [scan, { isLoading: isScanning }] = useScanMutation()
  const [invalidate, { isLoading: isInvalidating }] = useInvalidateSessionMutation()

  // Missing/undefined flags → treat as ENABLED (backward compatible).
  const orderEnabled = session.orderEnabled !== false
  const callWaiterEnabled = session.callWaiterEnabled !== false
  const arEnabled = session.arEnabled !== false
  const qrPaymentEnabled = session.qrPaymentEnabled !== false
  // Missing template/colour → classic, today's rendering, never a themed one.
  const menuTemplate = session.menuTemplate ?? 'classic'
  const menuAccentColor = session.menuAccentColor

  return {
    ...session,
    orderEnabled,
    callWaiterEnabled,
    arEnabled,
    qrPaymentEnabled,
    menuTemplate,
    menuAccentColor,
    hasSession: session.sessionToken !== null,
    isScanning,
    isInvalidating,
    scan,
    invalidate,
  }
}
