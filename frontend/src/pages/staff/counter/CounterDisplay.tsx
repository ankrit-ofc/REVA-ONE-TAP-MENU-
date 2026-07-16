import { useDispatch } from 'react-redux'
import { useGetBoardQuery, counterDisplayApi } from '@/features/counterDisplay/counterDisplayApi'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import type { AppDispatch } from '@/store/store'
import type { RealtimeEvent } from '@/types'
import type { DisplayBoardItem } from '@/lib/schemas/board'
import styles from './CounterDisplay.module.css'

/** status → display label + colour classes. Covers the full lifecycle. */
const STATUS_META: Record<string, { label: string; rowClass: string; statusClass: string }> = {
  NEW: { label: 'Ordered', rowClass: styles.rowNew, statusClass: styles.statusNew },
  PREPARING: { label: 'Preparing', rowClass: styles.rowPreparing, statusClass: styles.statusPreparing },
  READY: { label: 'Ready', rowClass: styles.rowReady, statusClass: styles.statusReady },
  SERVED: { label: 'Served', rowClass: styles.rowServed, statusClass: styles.statusServed },
}

/**
 * Passive wall board for the counter. Shows the full live lifecycle of recent
 * items — Ordered → Preparing → Ready → Served. SERVED rows are kept (not cleared)
 * so guests can see their food has gone out. Updates live over the staff WebSocket;
 * falls back to a slow poll.
 */
export default function CounterDisplay() {
  const dispatch = useDispatch<AppDispatch>()
  const { data: items, isLoading, isError } = useGetBoardQuery(undefined, {
    pollingInterval: 20_000,
  })

  useStaffRealtime((event: RealtimeEvent) => {
    if (event.type === 'order_item.status_changed' || event.type === 'order.created') {
      dispatch(counterDisplayApi.util.invalidateTags(['DisplayBoard']))
    }
  })

  const list = items ?? []

  return (
    <div className={styles.board}>
      <h1 className={styles.title}>Food Status</h1>

      {isLoading ? (
        <p className={styles.hint}>Loading…</p>
      ) : isError ? (
        <p className={styles.hint}>Unable to load the board.</p>
      ) : list.length === 0 ? (
        <p className={styles.hint}>No active orders yet.</p>
      ) : (
        <ul className={styles.list}>
          {list.map((item: DisplayBoardItem) => {
            const meta = STATUS_META[item.status] ?? STATUS_META.READY
            return (
              <li key={item.id} className={`${styles.row} ${meta.rowClass}`}>
                <div className={styles.left}>
                  <span className={styles.order}>#{item.order_number}</span>
                  <span className={styles.product}>
                    {item.quantity > 1 && <span className={styles.qty}>{item.quantity}× </span>}
                    {item.product_name}
                    {item.variant_name && <span className={styles.variant}> · {item.variant_name}</span>}
                  </span>
                </div>
                <div className={styles.right}>
                  <span className={styles.table}>{item.table_name}</span>
                  <span className={`${styles.status} ${meta.statusClass}`}>
                    {meta.label}
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
