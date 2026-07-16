import { useMarkPreparingMutation, useMarkReadyMutation } from '@/features/kitchen/kitchenApi'
import type { QueueItemResponse } from '@/lib/schemas/workflow'
import styles from './KitchenTicket.module.css'

interface Props {
  item: QueueItemResponse
}

export default function KitchenTicket({ item }: Props) {
  const [markPreparing, { isLoading: isPreparing }] = useMarkPreparingMutation()
  const [markReady, { isLoading: isMarkingReady }] = useMarkReadyMutation()

  const metas: string[] = []
  if (item.variant_name) metas.push(item.variant_name)
  if (item.addons.length > 0) metas.push(item.addons.map((a) => a.addon_name).join(', '))

  return (
    <div className={`${styles.ticket} ${styles[item.status]}`}>
      <div className={styles.header}>
        <span className={styles.orderNum}>#{item.order_number}</span>
        <span className={`${styles.badge} ${styles[`badge_${item.status}`]}`}>
          {item.status === 'NEW' ? 'New' : 'Preparing'}
        </span>
      </div>

      <div className={styles.product}>
        {item.quantity > 1 && <span className={styles.qty}>{item.quantity}×</span>}
        {item.product_name}
      </div>

      {metas.length > 0 && (
        <div className={styles.meta}>{metas.join(' · ')}</div>
      )}

      {item.special_instructions && (
        <div className={styles.instructions}>"{item.special_instructions}"</div>
      )}

      <div className={styles.actions}>
        {item.status === 'NEW' && (
          <button
            className={styles.btnPrepare}
            onClick={() => void markPreparing(item.id)}
            disabled={isPreparing}
          >
            {isPreparing ? 'Starting…' : 'Start Preparing'}
          </button>
        )}
        {item.status === 'PREPARING' && (
          <button
            className={styles.btnReady}
            onClick={() => void markReady(item.id)}
            disabled={isMarkingReady}
          >
            {isMarkingReady ? 'Marking…' : 'Mark Ready ✓'}
          </button>
        )}
      </div>
    </div>
  )
}
