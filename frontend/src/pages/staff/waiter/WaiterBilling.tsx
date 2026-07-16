import { useGetBillingEnabledQuery } from '@/features/waiter/waiterApi'
import CounterBilling from '@/pages/staff/counter/Billing'
import Loader from '@/components/common/Loader'

/**
 * Waiter billing surface — the exact counter screen, reused. Only available when
 * the admin has enabled `waiter_can_accept_payment`; otherwise a notice. The
 * backend independently enforces the same setting on the money operations.
 */
export default function WaiterBilling() {
  const { data, isLoading } = useGetBillingEnabledQuery()

  if (isLoading) return <Loader message="Loading…" />

  if (!data?.enabled) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
        <h1 style={{ fontSize: '1.25rem', marginBottom: '0.5rem', color: '#111827' }}>Billing</h1>
        <p>Billing is turned off for waiters at this restaurant.</p>
        <p style={{ fontSize: '0.875rem' }}>An admin can enable it in Settings.</p>
      </div>
    )
  }

  return <CounterBilling />
}
