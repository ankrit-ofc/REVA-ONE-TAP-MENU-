/**
 * Bill / payment page.
 *
 * Polls GET /invoices/my-order for the server-authoritative total until the
 * invoice is paid. Prices shown here come exclusively from the server.
 *
 * When payment completes, the order is closed and the table session is
 * invalidated server-side — so we CANNOT refetch (it would 401). Instead we
 * flip to a terminal "Paid — Thank you" screen straight from the realtime
 * `invoice.paid` / `order.closed` event (which arrives over the still-open WS).
 * That screen is a dead-end: to order again the guest re-scans the table QR,
 * which mints a fresh session.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { useGetMyOrderInvoiceQuery, useCreateGatewayIntentMutation } from '@/features/invoices/invoicesApi'
import { useGetCurrentOrderQuery } from '@/features/orders/ordersApi'
import { useCustomerRealtime } from '@/features/realtime/useRealtime'
import { useSession } from '@/features/session/useSession'
import { endCustomerSession } from '@/features/session/endSession'
import type { AppDispatch } from '@/store/store'
import PriceSummary from '@/components/ui/PriceSummary'
import Button from '@/components/common/Button'
import Loader from '@/components/common/Loader'
import { formatPrice } from '@/lib/currency'
import { estimateItemLine, estimateOrderTotal } from '@/lib/orderTotals'
import type { RealtimeEvent } from '@/types'
import styles from './BillRequest.module.css'

const CURRENCY = 'NPR'

export default function BillRequest() {
  const navigate = useNavigate()
  const dispatch = useDispatch<AppDispatch>()
  const { sessionToken } = useSession()

  const [paid, setPaid] = useState(false)
  const [paidInfo, setPaidInfo] = useState<{ invoiceNumber?: string; total?: number }>({})

  // Stop polling/refetching once paid — the session is invalidated and the call
  // would only 401. We render the terminal screen from the event instead.
  const { data: invoice, isLoading } = useGetMyOrderInvoiceQuery(undefined, {
    pollingInterval: paid ? 0 : 10_000,
    skip: paid,
  })

  // The live order — used to show an itemized estimate while the invoice (the
  // authoritative bill) is still being prepared. Skipped once paid (the session
  // is invalidated then, so the call would 401).
  const { data: order } = useGetCurrentOrderQuery(undefined, {
    pollingInterval: paid ? 0 : 30_000,
    skip: paid,
  })

  const [createIntent, { isLoading: isInitiatingPayment, data: intentData }] =
    useCreateGatewayIntentMutation()

  function handleRealtimeEvent(event: RealtimeEvent) {
    if (event.type === 'invoice.paid') {
      const num = typeof event['invoice_number'] === 'string' ? event['invoice_number'] : undefined
      const total = typeof event['total'] === 'string' ? Number(event['total']) : undefined
      setPaidInfo({ invoiceNumber: num, total })
      setPaid(true)
      // Hard-terminate the table session: the guard immediately shows the terminal
      // "session ended" screen, blocking any return to the menu (incl. refresh/back).
      endCustomerSession(dispatch, { invoiceNumber: num, total })
    } else if (event.type === 'order.closed') {
      setPaid(true)
      endCustomerSession(dispatch)
    }
  }

  useCustomerRealtime(sessionToken, handleRealtimeEvent)

  async function handleStartPayment(gateway: 'esewa' | 'khalti' | 'fonepay') {
    if (!invoice) return
    try {
      const result = await createIntent({
        invoiceId: invoice.id,
        body: { gateway },
      }).unwrap()

      const redirectUrl =
        (result['payment_url'] as string | undefined) ??
        (result['redirect_url'] as string | undefined)

      if (redirectUrl) {
        window.location.href = redirectUrl
      }
    } catch {
      // error shown below
    }
  }

  const isPaid = paid || invoice?.status === 'PAID'

  // ── Terminal "Paid — Thank you" screen (dead-end; no back-to-menu/order) ──
  if (isPaid) {
    const number = paidInfo.invoiceNumber ?? invoice?.invoice_number
    const total = paidInfo.total ?? invoice?.total
    return (
      <div className={styles.page}>
        <div className={styles.thankYou}>
          <span className={styles.thankIcon} aria-hidden>✓</span>
          <h1 className={styles.thankTitle}>Paid — Thank you!</h1>
          {number && <p className={styles.thankSub}>Invoice {number}</p>}
          {typeof total === 'number' && (
            <p className={styles.thankTotal}>{formatPrice(total, CURRENCY)}</p>
          )}
          <p className={styles.thankNote}>Scan the table QR again to place a new order.</p>
        </div>
      </div>
    )
  }

  if (isLoading) return <Loader fullscreen message="Loading bill…" />

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button onClick={() => navigate('/order-status')} className={styles.backBtn}>
          ← Order
        </button>
        <h1 className={styles.title}>Bill</h1>
      </header>

      {!invoice ? (
        <>
          <div className={styles.waiting}>
            <span className={styles.waitingIcon}>⏳</span>
            <h2 className={styles.waitingTitle}>Preparing your bill</h2>
            <p className={styles.waitingText}>
              Staff is reviewing your order. This page will update automatically.
            </p>
          </div>

          {order && order.items.length > 0 && (
            <div className={styles.estList}>
              {order.items.map((item) => {
                const metas: string[] = []
                if (item.variant_name) metas.push(item.variant_name)
                if (item.addons.length > 0)
                  metas.push(item.addons.map((a) => a.addon_name).join(', '))
                return (
                  <div className={styles.estRow} key={item.id}>
                    <div className={styles.estName}>
                      {item.quantity > 1 && `${item.quantity}× `}
                      {item.product_name}
                      {metas.length > 0 && (
                        <span className={styles.estMeta}>{metas.join(' · ')}</span>
                      )}
                    </div>
                    <span className={styles.estPrice}>
                      {formatPrice(estimateItemLine(item), CURRENCY)}
                    </span>
                  </div>
                )
              })}
              <div className={styles.estTotalRow}>
                <span className={styles.estTotalLabel}>Estimated total</span>
                <span className={styles.estTotalAmount}>
                  {formatPrice(estimateOrderTotal(order.items), CURRENCY)}
                </span>
              </div>
              <p className={styles.estNote}>* Estimated — staff will confirm your final bill.</p>
            </div>
          )}
        </>
      ) : (
        <div className={styles.invoiceSection}>
          <p className={styles.invoiceNumber}>Invoice {invoice.invoice_number}</p>

          <PriceSummary
            mode="server"
            currency={CURRENCY}
            subtotal={invoice.subtotal}
            discount={invoice.discount}
            taxTotal={invoice.tax_total}
            total={invoice.total}
          />

          <div className={styles.status}>
            {invoice.status === 'PENDING_PAYMENT' && (
              <div className={styles.paymentOptions}>
                <p className={styles.payLabel}>Pay with:</p>
                <div className={styles.gatewayBtns}>
                  <Button
                    variant="primary"
                    onClick={() => void handleStartPayment('esewa')}
                    disabled={isInitiatingPayment}
                    style={{ flex: 1 }}
                  >
                    eSewa
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void handleStartPayment('khalti')}
                    disabled={isInitiatingPayment}
                    style={{ flex: 1 }}
                  >
                    Khalti
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void handleStartPayment('fonepay')}
                    disabled={isInitiatingPayment}
                    style={{ flex: 1 }}
                  >
                    Fonepay
                  </Button>
                </div>
                <p className={styles.cashNote}>
                  Or pay cash / card at the counter.
                </p>
              </div>
            )}
            {(invoice.status === 'DRAFT' || invoice.status === 'FAILED') && (
              <p className={styles.waitingText}>
                {invoice.status === 'FAILED'
                  ? 'Payment failed. Please try again or pay at the counter.'
                  : 'Bill is being finalised…'}
              </p>
            )}
          </div>

          {intentData && !('payment_url' in intentData) && (
            <pre className={styles.intentDebug}>
              {JSON.stringify(intentData, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
