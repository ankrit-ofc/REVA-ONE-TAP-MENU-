import { Link } from 'react-router-dom'
import {
  Armchair,
  ArrowUpRight,
  ChevronDown,
  Clock,
  FolderTree,
  PackagePlus,
  TrendingUp,
  Trophy,
  UtensilsCrossed,
  Users,
  Wallet,
} from 'lucide-react'
import {
  useListCategoriesQuery,
  useListProductsQuery,
  useListAddonsQuery,
  useListStaffQuery,
  useListTablesQuery,
  useGetActiveTablesQuery,
  useGetRevenueTodayQuery,
  useGetOrdersThisWeekQuery,
  useGetTopProductsQuery,
} from '@/features/admin/adminApi'
import type { ActiveTable } from '@/lib/schemas/admin'
import { formatPrice } from '@/lib/currency'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const STAT_ICONS = {
  Categories: FolderTree,
  Products: UtensilsCrossed,
  'Add-ons': PackagePlus,
  Staff: Users,
  Tables: Armchair,
} as const

interface StatItem {
  label: keyof typeof STAT_ICONS
  active: number | null // null while loading — never show a fake 0
  to: string
}

// Dashboard widgets poll as a fallback to the WS invalidation used elsewhere;
// 30 s matches the counter/waiter order queues so Active Tables stays live.
const POLL_MS = 30_000

function StatCard({ label, active, to }: StatItem) {
  const Icon = STAT_ICONS[label]
  return (
    <Link to={to} className="group focus-visible:outline-none">
      <Card className="transition-shadow group-hover:shadow-md group-focus-visible:ring-2 group-focus-visible:ring-ring">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardDescription>Active {label}</CardDescription>
          <Icon className="size-4 text-muted-foreground" aria-hidden />
        </CardHeader>
        <CardContent>
          <div className="flex items-end justify-between">
            <span className="text-2xl font-bold tabular-nums">{active ?? '—'}</span>
            <span className="flex items-center gap-0.5 text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
              Manage <ArrowUpRight className="size-3" aria-hidden />
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

/** "45m" or "1h 23m" since the table's earliest active order was placed. */
function openFor(iso: string): string {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000))
  if (mins < 60) return `${mins}m`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

function ActiveTableRow({ table }: { table: ActiveTable }) {
  return (
    <details className="group rounded-lg border">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <div className="flex min-w-0 items-center gap-3">
          <Armchair className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="truncate font-medium">{table.table_label}</span>
          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {table.order_count} {table.order_count === 1 ? 'order' : 'orders'}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1 tabular-nums">
            <Clock className="size-3.5" aria-hidden />
            {openFor(table.earliest_placed_at)}
          </span>
          <ChevronDown
            className="size-4 transition-transform group-open:rotate-180"
            aria-hidden
          />
        </div>
      </summary>
      <div className="space-y-3 border-t px-4 py-3">
        {table.orders.map((order) => (
          <div key={order.order_id}>
            <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
              <span className="font-medium text-foreground">#{order.order_number}</span>
              <span>{order.status}</span>
            </div>
            <ul className="space-y-0.5 text-sm">
              {order.items.map((item, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span className="truncate">{item.name}</span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">×{item.quantity}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  )
}

function ActiveTablesPanel() {
  const { data: tables, isLoading } = useGetActiveTablesQuery(undefined, {
    pollingInterval: POLL_MS,
  })

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>Active Tables</CardTitle>
        <CardDescription>
          Tables with an open, unbilled order — longest-waiting first
          {isLoading || !tables ? '' : ` — ${tables.length} occupied`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">
            Loading…
          </div>
        ) : !tables || tables.length === 0 ? (
          <div className="flex h-56 flex-col items-center justify-center gap-1 text-center">
            <Clock className="size-6 text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium">No active orders right now</p>
            <p className="text-xs text-muted-foreground">
              New orders appear here as tables place them.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {tables.map((t) => (
              <ActiveTableRow key={t.table_id} table={t} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function RevenueTodayCard() {
  const { data, isLoading } = useGetRevenueTodayQuery(undefined, { pollingInterval: POLL_MS })
  const value =
    isLoading || !data
      ? '—'
      : data.amount === null
        ? 'Not available yet'
        : formatPrice(data.amount, data.currency)
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription>Revenue today</CardDescription>
        <Wallet className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        <span className="text-2xl font-bold tabular-nums">{value}</span>
      </CardContent>
    </Card>
  )
}

function OrdersThisWeekCard() {
  const { data, isLoading } = useGetOrdersThisWeekQuery(undefined, { pollingInterval: POLL_MS })
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription>Orders this week</CardDescription>
        <TrendingUp className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        <span className="text-2xl font-bold tabular-nums">
          {isLoading || !data ? '—' : data.count}
        </span>
      </CardContent>
    </Card>
  )
}

function TopProductsCard() {
  const { data, isLoading } = useGetTopProductsQuery(undefined, { pollingInterval: POLL_MS })
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription>Top-selling products · last 7 days</CardDescription>
        <Trophy className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        {isLoading || !data ? (
          <span className="text-sm text-muted-foreground">—</span>
        ) : data.products.length === 0 ? (
          <span className="text-sm text-muted-foreground">No sales in the last 7 days.</span>
        ) : (
          <ol className="space-y-1.5 text-sm">
            {data.products.map((p, i) => (
              <li key={p.product_name} className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate">
                  <span className="mr-2 text-muted-foreground tabular-nums">{i + 1}.</span>
                  {p.product_name}
                </span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {p.quantity_sold} sold
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}

export default function AdminDashboard() {
  const { data: categories } = useListCategoriesQuery()
  const { data: products } = useListProductsQuery()
  const { data: addons } = useListAddonsQuery()
  const { data: staff } = useListStaffQuery()
  const { data: tables } = useListTablesQuery()

  const countActive = <T extends { is_active: boolean }>(list?: T[]) =>
    list ? list.filter((x) => x.is_active).length : null

  const stats: StatItem[] = [
    { label: 'Categories', active: countActive(categories), to: '/admin/categories' },
    { label: 'Products', active: countActive(products), to: '/admin/products' },
    { label: 'Add-ons', active: countActive(addons), to: '/admin/addons' },
    { label: 'Staff', active: countActive(staff), to: '/admin/staff' },
    { label: 'Tables', active: countActive(tables), to: '/admin/tables' },
  ]

  return (
    <div className="flex flex-col gap-4 p-4 md:gap-6 md:p-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight md:text-2xl">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Your restaurant at a glance.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 xl:grid-cols-5">
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ActiveTablesPanel />

        <div className="flex flex-col gap-4">
          <RevenueTodayCard />
          <OrdersThisWeekCard />
          <TopProductsCard />
        </div>
      </div>
    </div>
  )
}
