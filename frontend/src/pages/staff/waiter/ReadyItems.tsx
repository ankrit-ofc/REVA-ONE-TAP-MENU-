import { useState } from 'react'
import { useDispatch } from 'react-redux'
import {
  useGetReadyItemsQuery,
  useGetOpenOrdersQuery,
  useMarkServedMutation,
  useMarkMealFinishedMutation,
  waiterApi,
} from '@/features/waiter/waiterApi'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import type { AppDispatch } from '@/store/store'
import type { RealtimeEvent } from '@/types'
import type { QueueItemResponse } from '@/lib/schemas/workflow'
import type { CounterOrderSummary } from '@/lib/schemas/order'
import styles from './ReadyItems.module.css'

function groupByOrder(items: QueueItemResponse[]) {
  const map = new Map<string, { orderNumber: number; tableName: string | null; items: QueueItemResponse[] }>()
  for (const item of items) {
    const entry = map.get(item.order_id)
      ?? { orderNumber: item.order_number, tableName: item.table_name ?? null, items: [] }
    entry.items.push(item)
    map.set(item.order_id, entry)
  }
  return Array.from(map.entries())
    .map(([orderId, val]) => ({ orderId, ...val }))
    .sort((a, b) => a.orderNumber - b.orderNumber)
}

interface OrderGroupProps {
  orderId: string
  orderNumber: number
  tableName: string | null
  items: QueueItemResponse[]
}

// The to-serve queue mixes stages: kitchens that cook off the printed KOT never
// mark PREPARING/READY, so the waiter serves straight from NEW.
const STAGE_LABEL: Record<string, string> = {
  NEW: 'New',
  PREPARING: 'Preparing',
  READY: 'Ready',
}

function OrderGroup({ orderNumber, tableName, items }: OrderGroupProps) {
  const [markServed, { isLoading: isServing }] = useMarkServedMutation()

  return (
    <div className={styles.group}>
      <div className={styles.groupHeader}>
        <span className={styles.groupTable}>{tableName ?? `Order #${orderNumber}`}</span>
        <span className={styles.groupOrderNum}>Order #{orderNumber}</span>
      </div>

      <ul className={styles.itemList}>
        {items.map((item) => {
          const metas: string[] = []
          if (item.variant_name) metas.push(item.variant_name)
          if (item.addons.length > 0) metas.push(item.addons.map((a) => a.addon_name).join(', '))

          return (
            <li key={item.id} className={styles.item}>
              <div className={styles.itemInfo}>
                <span className={styles.itemName}>
                  {item.quantity > 1 && `${item.quantity}× `}{item.product_name}
                  <span className={`${styles.stageChip} ${styles[`stage_${item.status}`] ?? ''}`}>
                    {STAGE_LABEL[item.status] ?? item.status}
                  </span>
                </span>
                {metas.length > 0 && (
                  <span className={styles.itemMeta}>{metas.join(' · ')}</span>
                )}
                {item.special_instructions && (
                  <span className={styles.itemNote}>"{item.special_instructions}"</span>
                )}
              </div>
              <button
                className={styles.btnServe}
                onClick={() => void markServed(item.id)}
                disabled={isServing}
              >
                Serve ✓
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ── Open Tables → move to billing (always visible) ───────────────────────────

function WaiterOpenOrders() {
  const dispatch = useDispatch<AppDispatch>()
  const { data: orders, isLoading } = useGetOpenOrdersQuery(undefined, {
    pollingInterval: 30_000,
  })
  const [markMealFinished] = useMarkMealFinishedMutation()
  const [movingId, setMovingId] = useState<string | null>(null)

  // Sound/notification for bill.requested is handled centrally in StaffLayout
  // (useStaffAlerts); here we only refresh the list.
  useStaffRealtime((event: RealtimeEvent) => {
    if (
      event.type === 'order.created' ||
      event.type === 'order.status_changed' ||
      event.type === 'bill.requested'
    ) {
      dispatch(waiterApi.util.invalidateTags(['WaiterOpenOrders']))
    }
  })

  const handleFinish = async (orderId: string) => {
    setMovingId(orderId)
    try {
      await markMealFinished(orderId).unwrap()
    } catch {
      // surfaced via the list refresh; transition errors are rare here
    } finally {
      setMovingId(null)
    }
  }

  const list = orders ?? []
  if (isLoading || list.length === 0) return null

  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Open Tables</h2>
      <div className={styles.openList}>
        {list.map((order: CounterOrderSummary) => (
          <div
            key={order.id}
            className={`${styles.openRow} ${order.bill_requested ? styles.openRowRequested : ''}`}
          >
            <span className={styles.openTable}>{order.table_name}</span>
            <span className={styles.openNum}>Order #{order.order_number}</span>
            {order.bill_requested
              ? <span className={styles.requestBadge}>🔔 Bill requested</span>
              : <span className={styles.openItems}>Awaiting guest's bill request</span>}
            <span className={styles.openItems}>
              {order.item_count} item{order.item_count !== 1 ? 's' : ''}
            </span>
            <button
              className={styles.btnFinish}
              onClick={() => void handleFinish(order.id)}
              disabled={!order.bill_requested || movingId === order.id}
            >
              {movingId === order.id ? 'Finishing…' : 'Finish Meal'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function WaiterReadyItems() {
  const dispatch = useDispatch<AppDispatch>()
  const { data: items, isLoading, isError } = useGetReadyItemsQuery(undefined, {
    pollingInterval: 30_000,
  })

  useStaffRealtime((event: RealtimeEvent) => {
    if (
      event.type === 'order_item.status_changed' ||
      event.type === 'order.status_changed' ||
      // New items enter the to-serve queue at creation (gate off) or at
      // approval (gate on) — refresh on both.
      event.type === 'order.created' ||
      event.type === 'order.approval_decided'
    ) {
      dispatch(waiterApi.util.invalidateTags(['WaiterQueue']))
    }
  })

  if (isLoading) {
    return <div className={styles.state}><p>Loading items…</p></div>
  }

  if (isError) {
    return (
      <div className={styles.state}>
        <p className={styles.stateError}>Failed to load items to serve.</p>
      </div>
    )
  }

  const groups = groupByOrder(items ?? [])

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>To Serve</h1>
        <span className={styles.count}>{items?.length ?? 0} item{(items?.length ?? 0) !== 1 ? 's' : ''}</span>
      </header>

      <WaiterOpenOrders />

      {groups.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>🍽️</div>
          <p>Nothing to serve right now.</p>
        </div>
      ) : (
        <div className={styles.groups}>
          {groups.map((g) => (
            <OrderGroup
              key={g.orderId}
              orderId={g.orderId}
              orderNumber={g.orderNumber}
              tableName={g.tableName}
              items={g.items}
            />
          ))}
        </div>
      )}
    </div>
  )
}
