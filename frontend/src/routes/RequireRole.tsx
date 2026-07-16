/**
 * UX-only route guard. Redirects to loginPath if the user is not authenticated
 * or does not hold one of the required roles.
 *
 * This is NOT a security boundary — the backend enforces roles on every request.
 * This guard only prevents staff from accidentally landing on the wrong surface.
 */
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import type { Role } from '@/types'

interface Props {
  roles: Role[]
  redirectTo?: string
}

export default function RequireRole({ roles, redirectTo = '/login' }: Props) {
  const { isAuthenticated, role } = useAuth()

  if (!isAuthenticated || role === null || !roles.includes(role)) {
    return <Navigate to={redirectTo} replace />
  }

  return <Outlet />
}
