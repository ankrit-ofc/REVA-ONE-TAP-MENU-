import { useState } from 'react'
import { useDispatch } from 'react-redux'
import {
  useApproveOrderItemsMutation,
  useGetOpenOrdersQuery,
  useGetPendingApprovalsQuery,
  useRejectOrderItemsMutation,
  waiterApi,
} from '@/features/waiter/waiterApi'
import { usePrintKotMutation } from '@/features/counter/counterApi'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import type { AppDispatch } from '@/store/store'
import type { CounterOrderSummary } from '@/lib/schemas/order'
import type { QueueItemResponse } from '@/lib/schemas/workflow'
import type { RealtimeEvent } from '@/types'
import styles from './WaiterOrders.module.css'

function errDetail(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'data' in e) {
    const d = (e as { data?: { detail?: string } }).data
    if (d?.detail) return d.detail
  }
  return 'Action failed'
}

/**
 * Approve/Reject panel shown on orders with items awaiting waiter approval
 * (require_order_approval). Approving releases the batch to the kitchen and
 * prints the KOT; rejecting cancels it (optional reason, audited).
 */
function PendingApprovalPanel({
  orderId,
  items,
}: {
  orderId: string
  items: QueueItemResponse[]
}) {
  const [approve, { isLoading: approving }] = useApproveOrderItemsMutation()
  const [reject, { isLoading: rejecting }] = useRejectOrderItemsMutation()
  const [confirmReject, setConfirmReject] = useState(false)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const busy = approving || rejecting

  const onApprove = async () => {
    setErr(null)
    try {
      await approve({ orderId }).unwrap()
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  const onReject = async () => {
    setErr(null)
    const trimmed = reason.trim()
    if (trimmed && trimmed.length < 3) {
      setErr('Reason must be at least 3 characters (or left empty).')
      return
    }
    try {
      await reject({ orderId, reason: trimmed || undefined }).unwrap()
      setConfirmReject(false)
      setReason('')
    } catch (e) {
      setErr(errDetail(e))
    }
  }

  return (
    <div className={styles.pendingBox}>
      <ul className={styles.pendingList}>
        {items.map((it) => (
          <li key={it.id} className={styles.pendingItem}>
            <span className={styles.pendingQty}>{it.quantity}×</span>
            <span>
              {it.product_name}
              {it.variant_name ? ` (${it.variant_name})` : ''}
            </span>
            {it.special_instructions && (
              <span className={styles.pendingNote}>“{it.special_instructions}”</span>
            )}
          </li>
        ))}
      </ul>

      {confirmReject ? (
        <div className={styles.rejectConfirm}>
          <input
            className={styles.reasonInput}
            value={reason}
            onChange={(e) => setReason(e.target.value.slice(0, 500))}
            placeholder="Reason (optional)"
            maxLength={500}
          />
          <button
            className={styles.rejectBtn}
            onClick={() => void onReject()}
            disabled={busy}
          >
            {rejecting ? 'Rejecting…' : 'Confirm reject'}
          </button>
          <button
            className={styles.cancelBtn}
            onClick={() => { setConfirmReject(false); setReason(''); setErr(null) }}
            disabled={busy}
          >
            Back
          </button>
        </div>
      ) : (
        <div className={styles.pendingActions}>
          <button
            className={styles.approveBtn}
            onClick={() => void onApprove()}
            disabled={busy}
          >
            {approving ? 'Approving…' : '✓ Approve'}
          </button>
          <button
            className={styles.rejectBtn}
            onClick={() => setConfirmReject(true)}
            disabled={busy}
          >
            ✕ Reject
          </button>
        </div>
      )}
      {err && <p className={styles.pendingErr}>{err}</p>}
    </div>
  )
}

/**
 * Waiter "New Orders" — a live list of the restaurant's active (OPEN) orders. Each
 * row has a Print button that relays a kitchen ticket to the print station (the
 * counter/admin computer with the printer), so a waiter on a phone can print to the
 * restaurant's printer. Orders awaiting approval additionally show the pending
 * batch with Approve/Reject. The chimes are handled centrally (useStaffAlerts).
 */
function NewOrderRow({
  order,
  pendingItems,
}: {
  order: CounterOrderSummary
  pendingItems: QueueItemResponse[]
}) {
  const [printKot, { isLoading }] = usePrintKotMutation()
  const [done, setDone] = useState(false)
  const [err, setErr] = useState(false)
  const needsApproval = pendingItems.length > 0

  const onPrint = async () => {
    setErr(false)
    try {
      await printKot({ orderId: order.id }).unwrap()
      setDone(true)
      setTimeout(() => setDone(false), 4000)
    } catch {
      setErr(true)
    }
  }

  return (
    <div
      className={`${styles.row} ${order.bill_requested ? styles.rowRequested : ''} ${
        needsApproval ? styles.rowPending : ''
      }`}
    >
      <span className={styles.table}>{order.table_name}</span>
      <span className={styles.num}>Order #{order.order_number}</span>
      <span className={styles.items}>
        {order.item_count} item{order.item_count !== 1 ? 's' : ''}
      </span>
      {needsApproval && <span className={styles.badgePending}>⏳ Needs approval</span>}
      {order.bill_requested && <span className={styles.badge}>🔔 Bill requested</span>}
      <button
        className={`${styles.print} ${done ? styles.printDone : ''} ${err ? styles.printErr : ''}`}
        onClick={() => void onPrint()}
        disabled={isLoading}
      >
        {isLoading ? 'Sending…' : done ? 'Printed ✓' : err ? 'Retry' : '🖨 Print'}
      </button>
      {needsApproval && (
        <PendingApprovalPanel orderId={order.id} items={pendingItems} />
      )}
    </div>
  )
}

export default function WaiterOrders() {
  const dispatch = useDispatch<AppDispatch>()
  const { data: orders, isLoading, isError } = useGetOpenOrdersQuery(undefined, {
    pollingInterval: 30_000,
  })
  const { data: pending } = useGetPendingApprovalsQuery(undefined, {
    pollingInterval: 30_000,
  })

  // Keep the list live as orders arrive / change (sound is handled in StaffLayout).
  useStaffRealtime((event: RealtimeEvent) => {
    if (event.type === 'order.created' || event.type === 'order.status_changed') {
      dispatch(waiterApi.util.invalidateTags(['WaiterOpenOrders']))
    }
    if (
      event.type === 'order.approval_requested' ||
      event.type === 'order.approval_decided'
    ) {
      dispatch(waiterApi.util.invalidateTags(['WaiterOpenOrders', 'WaiterPending']))
    }
  })

  const list = orders ?? []
  const pendingByOrder = new Map<string, QueueItemResponse[]>()
  for (const item of pending ?? []) {
    const bucket = pendingByOrder.get(item.order_id)
    if (bucket) bucket.push(item)
    else pendingByOrder.set(item.order_id, [item])
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>New Orders</h1>
        <span className={styles.count}>{list.length} active</span>
      </header>

      <p className={styles.hint}>
        Tap Print to send a kitchen ticket to the restaurant's printer.
      </p>

      {isLoading ? (
        <div className={styles.state}><p>Loading orders…</p></div>
      ) : isError ? (
        <div className={styles.state}><p className={styles.stateError}>Failed to load orders.</p></div>
      ) : list.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>🧾</div>
          <p>No active orders right now.</p>
        </div>
      ) : (
        <div className={styles.list}>
          {list.map((order) => (
            <NewOrderRow
              key={order.id}
              order={order}
              pendingItems={pendingByOrder.get(order.id) ?? []}
            />
          ))}
        </div>
      )}
    </div>
  )
}
