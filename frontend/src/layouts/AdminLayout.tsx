import { Outlet } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import { useGetMeQuery } from '@/features/auth/authApi'
import AppShell from '@/components/AppShell'

/**
 * Admin surface layout: the shadcn-style AppShell around the routed page.
 * Auth/role guarding is done by RequireRole in AppRoutes (UX only — the
 * backend enforces authorization on every endpoint).
 */
export default function AdminLayout() {
  const { role, logout } = useAuth()
  const { data: me } = useGetMeQuery()

  const brand = me?.restaurant_name ?? '…'
  const displayName = me?.email ? me.email.split('@')[0] : '…'
  const initial = displayName.charAt(0).toUpperCase() || '?'

  return (
    <AppShell
      brand={brand}
      role={role ?? ''}
      userName={displayName}
      initial={initial}
      onLogout={() => void logout()}
    >
      <Outlet />
    </AppShell>
  )
}
