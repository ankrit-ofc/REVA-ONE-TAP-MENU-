import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Armchair,
  ArrowUpRight,
  Clock,
  FolderTree,
  PackagePlus,
  TrendingUp,
  Users,
  UtensilsCrossed,
  Wallet,
} from 'lucide-react'
import {
  useListCategoriesQuery,
  useListProductsQuery,
  useListAddonsQuery,
  useListStaffQuery,
  useListTablesQuery,
} from '@/features/admin/adminApi'
import {
  useGetCounterOpenOrdersQuery,
  useGetCounterOrdersQuery,
} from '@/features/counter/counterApi'
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

/** Bucket active orders (existing counter queues) into hours placed, today. */
function useOrdersByHour() {
  // ADMIN is authorized on these endpoints (backend: require_role COUNTER|ADMIN|WAITER).
  const { data: open, isLoading: l1 } = useGetCounterOpenOrdersQuery()
  const { data: finished, isLoading: l2 } = useGetCounterOrdersQuery()

  return useMemo(() => {
    const all = [...(open ?? []), ...(finished ?? [])]
    const today = new Date()
    const isToday = (iso: string) => {
      const d = new Date(iso)
      return (
        d.getFullYear() === today.getFullYear() &&
        d.getMonth() === today.getMonth() &&
        d.getDate() === today.getDate()
      )
    }
    const todays = all.filter((o) => isToday(o.created_at))
    const byHour = new Map<number, number>()
    for (const o of todays) {
      const h = new Date(o.created_at).getHours()
      byHour.set(h, (byHour.get(h) ?? 0) + 1)
    }
    const data = Array.from({ length: 24 }, (_, h) => ({
      hour: `${String(h).padStart(2, '0')}:00`,
      orders: byHour.get(h) ?? 0,
    }))
    return { data, total: todays.length, loading: l1 || l2 }
  }, [open, finished, l1, l2])
}

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

/** Metrics that need a backend stats endpoint that doesn't exist yet. */
function ComingSoonCard({ label, icon: Icon }: { label: string; icon: typeof Wallet }) {
  return (
    <Card className="border-dashed">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription>{label}</CardDescription>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
          Coming soon
        </span>
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
  const chart = useOrdersByHour()

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
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Active orders today</CardTitle>
            <CardDescription>
              Orders currently open or awaiting billing, by hour placed
              {chart.loading ? '' : ` — ${chart.total} right now`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {chart.loading ? (
              <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">
                Loading…
              </div>
            ) : chart.total === 0 ? (
              <div className="flex h-56 flex-col items-center justify-center gap-1 text-center">
                <Clock className="size-6 text-muted-foreground" aria-hidden />
                <p className="text-sm font-medium">No active orders right now</p>
                <p className="text-xs text-muted-foreground">
                  New orders appear here as tables place them.
                </p>
              </div>
            ) : (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chart.data} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
                    <defs>
                      <linearGradient id="ordersFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.5} />
                        <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      dataKey="hour"
                      tickLine={false}
                      axisLine={false}
                      interval={3}
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    />
                    <Tooltip
                      cursor={{ stroke: 'var(--border)' }}
                      contentStyle={{
                        background: 'var(--popover)',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        fontSize: 12,
                        color: 'var(--popover-foreground)',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="orders"
                      stroke="var(--chart-1)"
                      strokeWidth={2}
                      fill="url(#ordersFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <ComingSoonCard label="Revenue today" icon={Wallet} />
          <ComingSoonCard label="Orders this week" icon={TrendingUp} />
          <ComingSoonCard label="Top-selling products" icon={UtensilsCrossed} />
        </div>
      </div>
    </div>
  )
}
