import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { useGetCurrentOrderQuery, useRequestBillMutation, ordersApi } from '@/features/orders/ordersApi'
import { useCustomerRealtime } from '@/features/realtime/useRealtime'
import { useSession } from '@/features/session/useSession'
import { endCustomerSession } from '@/features/session/endSession'
import { isContactCaptured } from '@/features/session/qrStorage'
import ReceiptContactSheet from '@/components/customer/ReceiptContactSheet'
import OrderItemStatusCard from '@/components/ui/OrderItemStatus'
import Button from '@/components/common/Button'
import Loader from '@/components/common/Loader'
import { formatPrice } from '@/lib/currency'
import { estimateOrderTotal } from '@/lib/orderTotals'
import type { AppDispatch } from '@/store/store'
import type { RealtimeEvent } from '@/types'
import styles from './OrderStatus.module.css'

const CURRENCY = 'NPR'

export default function OrderStatus() {
  const navigate = useNavigate()
  const dispatch = useDispatch<AppDispatch>()
  const { sessionToken, orderEnabled } = useSession()

  const { data: order, isLoading, isError } = useGetCurrentOrderQuery(undefined, {
    pollingInterval: 30_000,
  })
  const [requestBill, { isLoading: isRequestingBill }] = useRequestBillMutation()
  const [showContactSheet, setShowContactSheet] = useState(false)

  // Signal staff (notify-only), then offer the emailed receipt. The bill request
  // is fired FIRST and its result is ignored, so the contact form can never
  // become a gate in front of it — skipping, failing, or ignoring the sheet all
  // still leave the guest with a requested bill.
  async function handleRequestBill() {
    try {
      await requestBill().unwrap()
    } catch {
      // best-effort signal; the bill page still loads
    }
    if (isContactCaptured()) {
      navigate('/bill')
      return
    }
    setShowContactSheet(true)
  }

  // Invalidate the order cache whenever a WS item/order event arrives.
  function handleRealtimeEvent(event: RealtimeEvent) {
    // Payment closed the order → terminate the session (guard shows the dead-end
    // screen). Covers the case where the guest is still on this page at payment.
    if (event.type === 'order.closed' || event.type === 'invoice.paid') {
      endCustomerSession(dispatch)
      return
    }
    if (
      event.type === 'order_item.status_changed' ||
      event.type === 'order.status_changed' ||
      // Waiter approved/rejected a pending batch (or a new batch got gated) —
      // refresh so the "waiting for confirmation" badges update live.
      event.type === 'order.approval_requested' ||
      event.type === 'order.approval_decided'
    ) {
      dispatch(ordersApi.util.invalidateTags(['CurrentOrder']))
    }
  }

  useCustomerRealtime(sessionToken, handleRealtimeEvent)

  // If order is closed, navigate to bill page
  useEffect(() => {
    if (order?.status === 'CLOSED') {
      navigate('/bill', { replace: true })
    }
  }, [order?.status, navigate])

  if (isLoading) return <Loader fullscreen message="Loading your order…" />

  // The bill has ALREADY been requested by the time this renders — the sheet is
  // an offer layered on top, and either action below continues to the bill page.
  if (showContactSheet) {
    return (
      <div className={styles.page}>
        <ReceiptContactSheet
          skipLabel="No thanks, just show my bill"
          onDone={() => {
            setShowContactSheet(false)
            navigate('/bill')
          }}
        />
      </div>
    )
  }

  if (isError || !order) {
    return (
      <div className={styles.emptyState}>
        <span className={styles.emptyIcon}>🛒</span>
        <p>No active order. Ready to order?</p>
        <Button variant="secondary" onClick={() => navigate('/menu')}>
          Browse Menu
        </Button>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.orderNum}>Order #{order.order_number}</div>
        <span className={`${styles.statusBadge} ${styles[order.status]}`}>
          {order.status === 'OPEN' ? 'In Progress' : 'Meal Finished'}
        </span>
      </header>

      {order.items.some((item) => item.status === 'PENDING_APPROVAL') && (
        <div className={styles.approvalBanner}>
          A waiter will confirm your latest items shortly.
        </div>
      )}

      <section className={styles.items}>
        {order.items.map((item) => (
          <OrderItemStatusCard key={item.id} item={item} />
        ))}
      </section>

      <div className={styles.actions}>
        {order.status === 'OPEN' && (
          <>
            {order.items.length > 0 && (
              <div className={styles.totalBanner}>
                <div className={styles.totalRow}>
                  <span className={styles.totalLabel}>Your total is</span>
                  <span className={styles.totalAmount}>
                    {formatPrice(estimateOrderTotal(order.items), CURRENCY)}
                  </span>
                </div>
                <p className={styles.totalNote}>* Estimated — final total confirmed at billing.</p>
              </div>
            )}
            {orderEnabled && (
            <Button
              variant="secondary"
              onClick={() => navigate('/menu')}
              style={{ width: '100%', marginBottom: '0.75rem' }}
            >
              + Add More Items
            </Button>
            )}
            {orderEnabled && (
            <Button
              onClick={() => void handleRequestBill()}
              style={{ width: '100%' }}
              disabled={isRequestingBill || order.items.length === 0}
            >
              {isRequestingBill ? 'Requesting…' : 'Request Bill'}
            </Button>
            )}
          </>
        )}
        {order.status === 'MEAL_FINISHED' && (
          <div className={styles.waitingBill}>
            <p>Staff is preparing your bill…</p>
            <Button onClick={() => navigate('/bill')} style={{ width: '100%' }}>
              View Bill
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
