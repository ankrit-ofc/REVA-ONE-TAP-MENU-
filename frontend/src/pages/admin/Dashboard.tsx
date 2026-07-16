import { useNavigate } from 'react-router-dom'
import {
  useListCategoriesQuery,
  useListProductsQuery,
  useListAddonsQuery,
  useListStaffQuery,
  useListTablesQuery,
} from '@/features/admin/adminApi'
import styles from './Dashboard.module.css'

interface StatItem {
  label: string
  active: number
  to: string
}

export default function AdminDashboard() {
  const navigate = useNavigate()
  const { data: categories } = useListCategoriesQuery()
  const { data: products } = useListProductsQuery()
  const { data: addons } = useListAddonsQuery()
  const { data: staff } = useListStaffQuery()
  const { data: tables } = useListTablesQuery()

  const countActive = <T extends { is_active: boolean }>(list?: T[]) =>
    list?.filter((x) => x.is_active).length ?? 0

  const stats: StatItem[] = [
    { label: 'Categories', active: countActive(categories), to: '/admin/categories' },
    { label: 'Products', active: countActive(products), to: '/admin/products' },
    { label: 'Add-ons', active: countActive(addons), to: '/admin/addons' },
    { label: 'Staff', active: countActive(staff), to: '/admin/staff' },
    { label: 'Tables', active: countActive(tables), to: '/admin/tables' },
  ]

  return (
    <div className={styles.root}>
      <h1 className={styles.title}>Dashboard</h1>

      <div className={styles.stats}>
        {stats.map((s) => (
          <button key={s.label} className={styles.stat} onClick={() => navigate(s.to)}>
            <div className={styles.statValue}>{s.active}</div>
            <div className={styles.statLabel}>Active {s.label}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
