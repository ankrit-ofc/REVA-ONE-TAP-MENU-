import { useDispatch } from 'react-redux'
import { useGetKitchenQueueQuery, kitchenApi } from '@/features/kitchen/kitchenApi'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import KitchenTicket from '@/components/ui/KitchenTicket'
import type { AppDispatch } from '@/store/store'
import type { RealtimeEvent } from '@/types'
import type { QueueItemResponse } from '@/lib/schemas/workflow'
import styles from './Queue.module.css'

function groupByOrder(items: QueueItemResponse[]) {
  const map = new Map<number, QueueItemResponse[]>()
  for (const item of items) {
    const group = map.get(item.order_number) ?? []
    group.push(item)
    map.set(item.order_number, group)
  }
  return Array.from(map.entries()).sort(([a], [b]) => a - b)
}

export default function KitchenQueue() {
  const dispatch = useDispatch<AppDispatch>()
  const { data: items, isLoading, isError } = useGetKitchenQueueQuery(undefined, {
    pollingInterval: 30_000,
  })

  useStaffRealtime((event: RealtimeEvent) => {
    if (
      event.type === 'order.created' ||
      event.type === 'order_item.status_changed'
    ) {
      dispatch(kitchenApi.util.invalidateTags(['KitchenQueue']))
    }
  })

  if (isLoading) {
    return (
      <div className={styles.state}>
        <p>Loading queue…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className={styles.state}>
        <p className={styles.error}>Failed to load kitchen queue. Check your connection.</p>
      </div>
    )
  }

  const groups = groupByOrder(items ?? [])

  if (groups.length === 0) {
    return (
      <div className={styles.empty}>
        <div className={styles.emptyIcon}>🍳</div>
        <p>All caught up — no pending items.</p>
      </div>
    )
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Kitchen Queue</h1>
        <span className={styles.count}>{items?.length ?? 0} item{(items?.length ?? 0) !== 1 ? 's' : ''}</span>
      </header>

      <div className={styles.board}>
        {groups.map(([orderNumber, orderItems]) => (
          <div key={orderNumber} className={styles.orderGroup}>
            <div className={styles.orderLabel}>Order #{orderNumber}</div>
            <div className={styles.tickets}>
              {orderItems.map((item) => (
                <KitchenTicket key={item.id} item={item} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
