import type { OrderItemResponse } from '@/lib/schemas/order'
import styles from './OrderItemStatus.module.css'

const STATUS_LABELS: Record<string, string> = {
  PENDING_APPROVAL: 'Waiting for confirmation',
  NEW: 'Order Received',
  PREPARING: 'Preparing',
  READY: 'Ready to serve, pls wait',
  SERVED: 'Served',
  CANCELLED: 'Cancelled',
}

interface Props {
  item: OrderItemResponse
}

export default function OrderItemStatusCard({ item }: Props) {
  const label = STATUS_LABELS[item.status] ?? item.status
  const badgeClass = styles[item.status as keyof typeof styles] ?? styles.NEW

  const metas: string[] = []
  if (item.variant_name) metas.push(item.variant_name)
  if (item.addons.length > 0)
    metas.push(item.addons.map((a) => a.addon_name).join(', '))
  if (item.special_instructions)
    metas.push(`"${item.special_instructions}"`)

  return (
    <div className={styles.item}>
      <div className={styles.info}>
        <div className={styles.name}>
          {item.quantity > 1 && `${item.quantity}× `}
          {item.product_name}
        </div>
        {metas.length > 0 && (
          <div className={styles.meta}>{metas.join(' · ')}</div>
        )}
      </div>
      <span className={`${styles.badge} ${badgeClass}`}>{label}</span>
    </div>
  )
}
