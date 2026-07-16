import { useSelector } from 'react-redux'
import type { RootState } from '@/store/store'
import { useScanMutation, useInvalidateSessionMutation } from './sessionApi'

export function useSession() {
  const session = useSelector((state: RootState) => state.session)
  const [scan, { isLoading: isScanning }] = useScanMutation()
  const [invalidate, { isLoading: isInvalidating }] = useInvalidateSessionMutation()

  return {
    ...session,
    hasSession: session.sessionToken !== null,
    isScanning,
    isInvalidating,
    scan,
    invalidate,
  }
}
