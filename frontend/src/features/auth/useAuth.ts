import { useSelector } from 'react-redux'
import type { RootState } from '@/store/store'
import { useLogoutMutation } from './authApi'

export function useAuth() {
  const auth = useSelector((state: RootState) => state.auth)
  const [logoutMutation, { isLoading: isLoggingOut }] = useLogoutMutation()

  return {
    ...auth,
    isLoggingOut,
    logout: () => logoutMutation(),
  }
}
