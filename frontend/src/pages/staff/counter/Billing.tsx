import { useState, useRef } from 'react'
import { useDispatch } from 'react-redux'
import {
  useGetCounterOrdersQuery,
  useGetCounterOpenOrdersQuery,
  useMarkMealFinishedMutation,
  useReopenCounterOrderMutation,
  useStartBillingMutation,
  useCloseUnpaidMutation,
  useQuickBillMutation,
  useGenerateInvoiceMutation,
  useGetInvoiceQuery,
  useLazyGetReceiptQuery,
  usePayInvoiceMutation,
  useManualOverrideMutation,
  counterApi,
  type CounterPayMethod,
} from '@/features/counter/counterApi'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import { useAuth } from '@/features/auth/useAuth'
import PriceSummary from '@/components/ui/PriceSummary'
import { resolveDevice } from '@/features/printing/printerDevices'
import { buildBillBytes } from '@/features/printing/receipts'
import { sendBytes, describePrinterError } from '@/lib/escpos/webusbPrinter'
import type { AppDispatch } from '@/store/store'
import type { CounterOrderSummary } from '@/lib/schemas/order'
import type { ReceiptResponse } from '@/lib/schemas/invoice'
import type { RealtimeEvent } from '@/types'
import { useOnEscape } from '@/lib/useOnEscape'
import styles from './Billing.module.css'

const MIN_OVERRIDE_REASON = 3
const MAX_OVERRIDE_REASON = 500

function errDetail(e: unknown): string {
  if (!e) return 'Unknown error'
  if (typeof e === 'object' && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  if (typeof e === 'object' && 'message' in e) return String((e as { message?: string }).message)
  return 'Request failed'
}

const esc = (s: string) =>
  s.replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c] as string))

/** Fallback: opens an itemized, print-friendly receipt in a new window (used when
 * no thermal printer is paired in this browser). */
function printReceiptHtml(r: ReceiptResponse): void {
  const win = window.open('', '_blank', 'width=380,height=720')
  if (!win) return
  const money = (n: number) => `${r.currency} ${n.toFixed(2)}`
  const lines = r.items
    .map((it) => {
      const name = it.variant_name ? `${it.product_name} (${it.variant_name})` : it.product_name
      const addons = it.addons
        .map((a) => `<div class="row sub"><span>+ ${esc(a.addon_name)}</span><span>${money(a.addon_price)}</span></div>`)
        .join('')
      return `<div class="row"><span>${it.quantity} × ${esc(name)}</span><span>${money(it.line_total)}</span></div>${addons}`
    })
    .join('')
  win.document.write(`<!doctype html><html><head><title>${esc(r.invoice_number)}</title>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;color:#111;max-width:300px;margin:0 auto;padding:18px}
  h1{font-size:16px;text-align:center;margin:0 0 2px}
  .sub2{text-align:center;color:#666;font-size:12px;margin:0 0 12px}
  .row{display:flex;justify-content:space-between;font-size:13px;margin:4px 0}
  .row.sub{color:#666;font-size:12px;padding-left:10px}
  .div{border-top:1px dashed #999;margin:8px 0}
  .total{font-weight:800;font-size:15px}
</style></head><body>
<h1>${esc(r.restaurant_name)}</h1>
<p class="sub2">${esc(r.invoice_number)} · Table ${esc(r.table_name)} · Order #${r.order_number}</p>
<div class="div"></div>
${lines}
<div class="div"></div>
<div class="row"><span>Subtotal</span><span>${money(r.subtotal)}</span></div>
${r.discount > 0 ? `<div class="row"><span>Discount</span><span>- ${money(r.discount)}</span></div>` : ''}
<div class="row"><span>Tax</span><span>${money(r.tax_total)}</span></div>
<div class="div"></div>
<div class="row total"><span>TOTAL</span><span>${money(r.total)}</span></div>
${r.payment_method ? `<p class="sub2">Paid: ${esc(r.payment_method)}</p>` : ''}
</body></html>`)
  win.document.close()
  win.focus()
  win.print()
}

// ── Shared reason modal (Reopen / Close-without-payment) ─────────────────────

interface ReasonModalProps {
  title: string
  hint: string
  confirmLabel: string
  busy: boolean
  onConfirm: (reason: string) => void
  onClose: () => void
}

function ReasonModal({ title, hint, confirmLabel, busy, onConfirm, onClose }: ReasonModalProps) {
  const [reason, setReason] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const ok = reason.trim().length >= 3
  useOnEscape(onClose)

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <h2 className={styles.modalTitle}>{title}</h2>
        <p className={styles.modalHint}>{hint}</p>
        <textarea
          className={styles.reasonInput}
          rows={3}
          maxLength={500}
          placeholder="Reason (required, min 3 chars)…"
          value={reason}
          onChange={(e) => setReason(e.target.value.slice(0, 500))}
        />
        <div className={styles.charCount}>{reason.length}/500</div>
        {err && <p className={styles.formError}>{err}</p>}
        <div className={styles.modalActions}>
          <button type="button" className={styles.btnCancelOverride} onClick={onClose}>Cancel</button>
          <button
            type="button"
            className={styles.btnConfirmOverride}
            disabled={!ok || busy}
            onClick={() => { setErr(null); onConfirm(reason.trim()) }}
          >
            {busy ? '…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Method picker (one-tap Bill & Clear) ─────────────────────────────────────

interface MethodModalProps {
  order: CounterOrderSummary
  busy: boolean
  error: string | null
  onConfirm: (method: CounterPayMethod) => void
  onClose: () => void
}

function MethodModal({ order, busy, error, onConfirm, onClose }: MethodModalProps) {
  const [method, setMethod] = useState<CounterPayMethod>('CASH')
  useOnEscape(onClose)

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <h2 className={styles.modalTitle}>Bill &amp; clear #{order.order_number}</h2>
        <p className={styles.modalHint}>
          Records payment for {order.table_name} and clears the table. Choose how the guest paid.
        </p>
        <div className={styles.methodButtons}>
          {(['CASH', 'CARD', 'COUNTER_WALLET'] as CounterPayMethod[]).map((m) => (
            <button
              key={m}
              type="button"
              className={`${styles.methodBtn} ${method === m ? styles.methodBtnActive : ''}`}
              onClick={() => setMethod(m)}
            >
              {m === 'CASH' ? '💵 Cash' : m === 'CARD' ? '💳 Card' : '📱 Wallet'}
            </button>
          ))}
        </div>
        {error && <p className={styles.formError}>{error}</p>}
        <div className={styles.modalActions}>
          <button type="button" className={styles.btnCancelOverride} onClick={onClose}>Cancel</button>
          <button
            type="button"
            className={styles.btnConfirmOverride}
            disabled={busy}
            onClick={() => onConfirm(method)}
          >
            {busy ? '…' : 'Confirm & clear'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Step 0: OPEN orders → move to billing ────────────────────────────────────

function OpenOrders() {
  const dispatch = useDispatch<AppDispatch>()
  const { data: orders, isLoading } = useGetCounterOpenOrdersQuery(undefined, {
    pollingInterval: 15_000,
  })
  const [markMealFinished] = useMarkMealFinishedMutation()
  const [startBilling] = useStartBillingMutation()
  const [closeUnpaid, { isLoading: isClosing }] = useCloseUnpaidMutation()
  const [quickBill, { isLoading: isBilling }] = useQuickBillMutation()
  const [movingId, setMovingId] = useState<string | null>(null)
  const [startingId, setStartingId] = useState<string | null>(null)
  const [closeTarget, setCloseTarget] = useState<CounterOrderSummary | null>(null)
  const [billTarget, setBillTarget] = useState<CounterOrderSummary | null>(null)
  const [billErr, setBillErr] = useState<string | null>(null)
  // Stable idempotency key per Bill & Clear attempt — reused if the confirm is retried.
  const billKeyRef = useRef('')
  const [err, setErr] = useState<string | null>(null)

  // Sound/notification for bill.requested is handled centrally in StaffLayout
  // (useStaffAlerts); here we only refresh the list.
  useStaffRealtime((event: RealtimeEvent) => {
    if (
      event.type === 'order.created' ||
      event.type === 'order.status_changed' ||
      event.type === 'order.closed' ||
      event.type === 'bill.requested'
    ) {
      // bill.requested flips a table's flag → refetch so the button unlocks.
      dispatch(counterApi.util.invalidateTags(['CounterOpenOrders']))
    }
  })

  const handleMove = async (orderId: string) => {
    setErr(null)
    setMovingId(orderId)
    try {
      await markMealFinished(orderId).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    } finally {
      setMovingId(null)
    }
  }

  const handleStart = async (orderId: string) => {
    setErr(null)
    setStartingId(orderId)
    try {
      await startBilling(orderId).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    } finally {
      setStartingId(null)
    }
  }

  const handleClose = async (reason: string) => {
    if (!closeTarget) return
    setErr(null)
    try {
      await closeUnpaid({ orderId: closeTarget.id, reason }).unwrap()
      setCloseTarget(null)
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  const openBill = (order: CounterOrderSummary) => {
    billKeyRef.current = crypto.randomUUID()
    setBillErr(null)
    setBillTarget(order)
  }

  const handleQuickBill = async (method: CounterPayMethod) => {
    if (!billTarget) return
    setBillErr(null)
    try {
      await quickBill({
        orderId: billTarget.id,
        method,
        idempotencyKey: billKeyRef.current,
      }).unwrap()
      setBillTarget(null)
    } catch (e) {
      setBillErr(errDetail(e))
    }
  }

  const list = orders ?? []
  if (isLoading || list.length === 0) return null // hide the section when nothing is open

  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Open Tables</h2>
      <div className={styles.lookupCard}>
        <p className={styles.lookupHint}>Send a table to billing when the guests are ready to pay.</p>
        {err && <p className={styles.formError}>{err}</p>}
        <div className={styles.orderList}>
          {list.map((order: CounterOrderSummary) => (
            <div
              key={order.id}
              className={`${styles.openRow} ${order.bill_requested ? styles.openRowRequested : ''}`}
            >
              <span className={styles.orderNum}>#{order.order_number}</span>
              <span className={styles.orderTable}>{order.table_name}</span>
              {order.bill_requested
                ? <span className={styles.requestBadge}>🔔 Bill requested</span>
                : <span className={styles.orderItems}>Awaiting guest's bill request</span>}
              <span className={styles.orderItems}>
                {order.item_count} item{order.item_count !== 1 ? 's' : ''}
              </span>
              <div className={styles.rowActions}>
                {!order.bill_requested && (
                  <button
                    className={styles.btnSmall}
                    onClick={() => void handleStart(order.id)}
                    disabled={startingId === order.id}
                    title="Override: bill a guest who couldn't tap Request Bill"
                  >
                    {startingId === order.id ? '…' : 'Start billing'}
                  </button>
                )}
                {order.bill_requested && (
                  <button
                    className={styles.btnMove}
                    onClick={() => openBill(order)}
                    title="Bill this table with one tap and clear it"
                  >
                    Bill &amp; Clear
                  </button>
                )}
                <button
                  className={styles.btnSmall}
                  onClick={() => void handleMove(order.id)}
                  disabled={!order.bill_requested || movingId === order.id}
                  title="Move to the billing queue to add a discount or print an invoice"
                >
                  {movingId === order.id ? 'Moving…' : 'Move to Billing'}
                </button>
                <button className={styles.btnDanger} onClick={() => setCloseTarget(order)}>
                  Close
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {closeTarget && (
        <ReasonModal
          title={`Close #${closeTarget.order_number} without payment`}
          hint="Cancel / walkout / write-off — voids any invoice and closes the table with no payment recorded. This action is logged."
          confirmLabel="Close (no payment)"
          busy={isClosing}
          onConfirm={(reason) => void handleClose(reason)}
          onClose={() => setCloseTarget(null)}
        />
      )}

      {billTarget && (
        <MethodModal
          order={billTarget}
          busy={isBilling}
          error={billErr}
          onConfirm={(method) => void handleQuickBill(method)}
          onClose={() => setBillTarget(null)}
        />
      )}
    </div>
  )
}

// ── Step 1: MEAL_FINISHED order queue ────────────────────────────────────────

interface OrderQueueProps {
  onSelect: (orderId: string, discountType: 'flat' | 'percent', discountValue: number) => void
}

function OrderQueue({ onSelect }: OrderQueueProps) {
  const dispatch = useDispatch<AppDispatch>()
  const { data: orders, isLoading, isError, refetch } = useGetCounterOrdersQuery(undefined, {
    pollingInterval: 15_000,
  })
  const [discountType, setDiscountType] = useState<'flat' | 'percent'>('flat')
  const [discountValue, setDiscountValue] = useState('0')
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [generateInvoice, { isLoading: isGenerating }] = useGenerateInvoiceMutation()
  const [generateErr, setGenerateErr] = useState<string | null>(null)
  const [reopenOrder, { isLoading: isReopening }] = useReopenCounterOrderMutation()
  const [closeUnpaid, { isLoading: isClosing }] = useCloseUnpaidMutation()
  const [reopenTarget, setReopenTarget] = useState<CounterOrderSummary | null>(null)
  const [closeTarget, setCloseTarget] = useState<CounterOrderSummary | null>(null)

  useStaffRealtime((event: RealtimeEvent) => {
    if (
      event.type === 'order.status_changed' ||
      event.type === 'order.created' ||
      event.type === 'order.closed'
    ) {
      // order.closed = a table was just paid → it leaves the billing queue.
      dispatch(counterApi.util.invalidateTags(['CounterOrders']))
    }
  })

  const handleGenerate = async () => {
    if (!selectedOrderId) return
    setGenerateErr(null)
    const discount = parseFloat(discountValue) || 0
    if (discount < 0 || (discountType === 'percent' && discount > 100)) {
      setGenerateErr('Invalid discount value.')
      return
    }
    try {
      const inv = await generateInvoice({
        order_id: selectedOrderId,
        discount_type: discountType,
        discount_value: discount,
      }).unwrap()
      onSelect(inv.id, discountType, discount)
    } catch (e) {
      setGenerateErr(errDetail(e))
    }
  }

  const handleReopen = async (reason: string) => {
    if (!reopenTarget) return
    try {
      await reopenOrder({ orderId: reopenTarget.id, reason }).unwrap()
      setReopenTarget(null)
    } catch (e) {
      setGenerateErr(errDetail(e))
    }
  }

  const handleClose = async (reason: string) => {
    if (!closeTarget) return
    try {
      await closeUnpaid({ orderId: closeTarget.id, reason }).unwrap()
      setCloseTarget(null)
    } catch (e) {
      setGenerateErr(errDetail(e))
    }
  }

  if (isLoading) {
    return <div className={styles.lookupCard}><p className={styles.lookupHint}>Loading orders…</p></div>
  }

  if (isError) {
    return (
      <div className={styles.lookupCard}>
        <p className={styles.formError}>Failed to load orders.</p>
        <button className={styles.btnGenerate} onClick={() => void refetch()}>Retry</button>
      </div>
    )
  }

  const list = orders ?? []

  return (
    <div className={styles.lookupCard}>
      {list.length === 0 ? (
        <p className={styles.lookupHint}>No orders waiting for billing.</p>
      ) : (
        <>
          <p className={styles.lookupHint}>Select an order to generate an invoice.</p>
          <div className={styles.orderList}>
            {list.map((order: CounterOrderSummary) => (
              <div
                key={order.id}
                className={`${styles.orderRow} ${selectedOrderId === order.id ? styles.orderRowSelected : ''}`}
              >
                <button className={styles.orderSelect} onClick={() => setSelectedOrderId(order.id)}>
                  <span className={styles.orderNum}>#{order.order_number}</span>
                  <span className={styles.orderTable}>{order.table_name}</span>
                  <span className={styles.orderItems}>{order.item_count} item{order.item_count !== 1 ? 's' : ''}</span>
                </button>
                <div className={styles.rowActions}>
                  <button className={styles.btnSmall} onClick={() => setReopenTarget(order)}>Reopen</button>
                  <button className={styles.btnDanger} onClick={() => setCloseTarget(order)}>Close</button>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.discountRow}>
            <div className={styles.field}>
              <label className={styles.label}>Discount Type</label>
              <select
                className={styles.select}
                value={discountType}
                onChange={(e) => setDiscountType(e.target.value as 'flat' | 'percent')}
              >
                <option value="flat">Flat (NPR)</option>
                <option value="percent">Percent (%)</option>
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Discount Amount</label>
              <input
                className={styles.input}
                type="number"
                min="0"
                max={discountType === 'percent' ? 100 : undefined}
                step="0.01"
                value={discountValue}
                onChange={(e) => setDiscountValue(e.target.value)}
              />
            </div>
          </div>

          {generateErr && <p className={styles.formError}>{generateErr}</p>}

          <button
            className={styles.btnGenerate}
            onClick={() => void handleGenerate()}
            disabled={isGenerating || !selectedOrderId}
          >
            {isGenerating ? 'Generating…' : 'Generate Invoice'}
          </button>
        </>
      )}

      {reopenTarget && (
        <ReasonModal
          title={`Reopen #${reopenTarget.order_number}`}
          hint="Returns the order to OPEN so more items can be added. Requires a reason; only available when reopening is enabled in settings."
          confirmLabel="Reopen"
          busy={isReopening}
          onConfirm={(reason) => void handleReopen(reason)}
          onClose={() => setReopenTarget(null)}
        />
      )}
      {closeTarget && (
        <ReasonModal
          title={`Close #${closeTarget.order_number} without payment`}
          hint="Cancel / walkout / write-off — voids the invoice and closes the table with no payment recorded. This action is logged."
          confirmLabel="Close (no payment)"
          busy={isClosing}
          onConfirm={(reason) => void handleClose(reason)}
          onClose={() => setCloseTarget(null)}
        />
      )}
    </div>
  )
}

// ── Step 2: Invoice view + payment ───────────────────────────────────────────

interface InvoiceViewProps {
  invoiceId: string
  currency: string
  role: string | null
  onReset: () => void
}

function InvoiceView({ invoiceId, currency, role, onReset }: InvoiceViewProps) {
  const dispatch = useDispatch<AppDispatch>()
  const { data: invoice, isLoading } = useGetInvoiceQuery(invoiceId, {
    pollingInterval: 10_000,
  })

  const [payInvoice, { isLoading: isPaying }] = usePayInvoiceMutation()
  const [manualOverride, { isLoading: isOverriding }] = useManualOverrideMutation()
  const [fetchReceipt] = useLazyGetReceiptQuery()
  const [selectedMethod, setSelectedMethod] = useState<CounterPayMethod>('CASH')
  const [overrideReason, setOverrideReason] = useState('')
  const [showOverride, setShowOverride] = useState(false)
  const [payError, setPayError] = useState<string | null>(null)
  const [printErr, setPrintErr] = useState<string | null>(null)
  const [printing, setPrinting] = useState(false)

  const handlePrint = async () => {
    setPrintErr(null)
    setPrinting(true)
    try {
      const receipt = await fetchReceipt(invoiceId).unwrap()
      const device = await resolveDevice('bill')
      if (device) {
        await sendBytes(device, buildBillBytes(receipt, ''))
      } else {
        printReceiptHtml(receipt)
      }
    } catch (e) {
      setPrintErr(describePrinterError(e))
    } finally {
      setPrinting(false)
    }
  }

  // Stable idempotency key — generated once per invoice view, reused on retries
  const idempotencyKeyRef = useRef(crypto.randomUUID())

  useStaffRealtime((event: RealtimeEvent) => {
    if (event.type === 'invoice.paid' || event.type === 'order.closed') {
      dispatch(counterApi.util.invalidateTags(['CounterInvoice']))
    }
  })

  if (isLoading || !invoice) {
    return <div className={styles.state}><p>Loading invoice…</p></div>
  }

  const isPaid = invoice.status === 'PAID'
  const isClosed = invoice.status === 'VOID' || invoice.status === 'REFUNDED'

  const handlePay = async () => {
    setPayError(null)
    try {
      await payInvoice({
        invoiceId: invoice.id,
        method: selectedMethod,
        idempotencyKey: idempotencyKeyRef.current,
      }).unwrap()
    } catch (e) {
      setPayError(errDetail(e))
    }
  }

  const handleOverride = async (e: React.FormEvent) => {
    e.preventDefault()
    if (overrideReason.trim().length < MIN_OVERRIDE_REASON) return
    try {
      await manualOverride({ invoiceId: invoice.id, reason: overrideReason.trim() }).unwrap()
      setShowOverride(false)
    } catch (e) {
      setPayError(errDetail(e))
    }
  }

  return (
    <>
    <div className={styles.invoiceTopBar}>
      <button className={styles.btnBack} onClick={onReset}>← Go Back</button>
      <button className={styles.btnPrint} onClick={() => void handlePrint()} disabled={printing}>
        {printing ? '…' : '🖨 Print'}
      </button>
    </div>
    {printErr && <p className={styles.formError}>{printErr}</p>}
    <div className={styles.invoiceCard}>
      <div className={styles.invoiceHeader}>
        <div>
          <div className={styles.invoiceNumber}>{invoice.invoice_number}</div>
          <div className={`${styles.invoiceStatus} ${styles[`status_${invoice.status}`]}`}>
            {invoice.status}
          </div>
        </div>
      </div>

      <PriceSummary
        mode="server"
        currency={currency}
        subtotal={invoice.subtotal}
        discount={invoice.discount}
        taxTotal={invoice.tax_total}
        total={invoice.total}
      />

      {isPaid ? (
        <div className={styles.paid}>
          <span className={styles.paidIcon}>✓</span>
          <span>Payment recorded — {invoice.payment_method}</span>
        </div>
      ) : isClosed ? (
        <div className={styles.voided}>Invoice {invoice.status.toLowerCase()}</div>
      ) : (
        <>
          <div className={styles.methodSection}>
            <label className={styles.sectionLabel}>Payment Method</label>
            <div className={styles.methodButtons}>
              {(['CASH', 'CARD', 'COUNTER_WALLET'] as CounterPayMethod[]).map((m) => (
                <button
                  key={m}
                  className={`${styles.methodBtn} ${selectedMethod === m ? styles.methodBtnActive : ''}`}
                  onClick={() => setSelectedMethod(m)}
                >
                  {m === 'CASH' ? '💵 Cash' : m === 'CARD' ? '💳 Card' : '📱 Wallet'}
                </button>
              ))}
            </div>
          </div>

          {payError && <p className={styles.formError}>{payError}</p>}

          <button
            className={styles.btnPay}
            onClick={() => void handlePay()}
            disabled={isPaying}
          >
            {isPaying ? 'Processing…' : `Collect Payment — ${currency} ${invoice.total.toFixed(2)}`}
          </button>

          {role === 'ADMIN' && (
            <>
              {!showOverride ? (
                <button
                  className={styles.btnOverride}
                  onClick={() => setShowOverride(true)}
                >
                  Manual Override (Admin)
                </button>
              ) : (
                <form onSubmit={(e) => void handleOverride(e)} className={styles.overrideForm}>
                  <label className={styles.sectionLabel}>Override Reason (required)</label>
                  <textarea
                    className={styles.reasonInput}
                    value={overrideReason}
                    onChange={(e) => setOverrideReason(e.target.value.slice(0, MAX_OVERRIDE_REASON))}
                    maxLength={MAX_OVERRIDE_REASON}
                    rows={2}
                    placeholder="Reason for manual override…"
                  />
                  <div className={styles.charCount}>{overrideReason.length}/{MAX_OVERRIDE_REASON}</div>
                  <div className={styles.overrideActions}>
                    <button type="button" className={styles.btnCancelOverride} onClick={() => setShowOverride(false)}>
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className={styles.btnConfirmOverride}
                      disabled={overrideReason.trim().length < MIN_OVERRIDE_REASON || isOverriding}
                    >
                      {isOverriding ? 'Overriding…' : 'Confirm Override'}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </>
      )}
    </div>
    </>
  )
}

// ── Root component ────────────────────────────────────────────────────────────

export default function CounterBilling() {
  const { role } = useAuth()
  const [invoiceId, setInvoiceId] = useState<string | null>(null)

  const currency = 'NPR'

  if (invoiceId) {
    return (
      <div className={styles.root}>
        <h1 className={styles.title}>Counter Billing</h1>
        <InvoiceView
          invoiceId={invoiceId}
          currency={currency}
          role={role}
          onReset={() => setInvoiceId(null)}
        />
      </div>
    )
  }

  return (
    <div className={styles.root}>
      <h1 className={styles.title}>Counter Billing</h1>
      <OpenOrders />
      <h2 className={styles.sectionTitle}>Ready for Billing</h2>
      <OrderQueue onSelect={(id) => setInvoiceId(id)} />
    </div>
  )
}
