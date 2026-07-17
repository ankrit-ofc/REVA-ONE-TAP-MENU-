import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  Armchair,
  ChevronDown,
  FolderTree,
  LayoutDashboard,
  LogOut,
  PackagePlus,
  PanelLeft,
  Printer,
  Settings,
  Users,
  UtensilsCrossed,
  X,
} from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import '@/styles/admin.css'

/** The CURRENT admin nav, unchanged — same routes, same order, same guard. */
const NAV_ITEMS = [
  { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/admin/categories', label: 'Categories', icon: FolderTree },
  { to: '/admin/products', label: 'Products', icon: UtensilsCrossed },
  { to: '/admin/addons', label: 'Add-ons', icon: PackagePlus },
  { to: '/admin/staff', label: 'Staff', icon: Users },
  { to: '/admin/tables', label: 'Tables', icon: Armchair },
  { to: '/admin/devices', label: 'Devices', icon: Printer },
  { to: '/admin/settings', label: 'Settings', icon: Settings },
]

interface AppShellProps {
  brand: string
  role: string
  userName: string
  initial: string
  onLogout: () => void
  children: ReactNode
}

function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  return (
    <ul className="flex flex-col gap-1 px-2">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/85 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                collapsed && 'justify-center px-2',
                isActive && 'bg-sidebar-accent text-sidebar-accent-foreground shadow-sm',
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        </li>
      ))}
    </ul>
  )
}

function SidebarHeader({ brand, role, collapsed }: { brand: string; role: string; collapsed: boolean }) {
  return (
    <div className={cn('flex items-center gap-3 px-4 py-4', collapsed && 'justify-center px-2')}>
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary font-bold text-sidebar-primary-foreground">
        {brand.charAt(0).toUpperCase() || 'R'}
      </div>
      {!collapsed && (
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white" title={brand}>{brand}</div>
          <div className="text-[0.65rem] font-bold uppercase tracking-wider text-sidebar-primary">{role}</div>
        </div>
      )}
    </div>
  )
}

/**
 * shadcn-style dashboard shell (sidebar-07 flavour): collapsible icon sidebar
 * on desktop, overlay drawer on mobile, breadcrumb top bar, avatar dropdown
 * with the existing logout flow. Route guarding stays in AppRoutes/RequireRole.
 */
export default function AppShell({ brand, role, userName, initial, onLogout, children }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  // Lock background scroll while the mobile drawer is open (same behaviour as
  // the previous CSS-modules layout).
  useEffect(() => {
    if (!mobileOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [mobileOpen])

  const current =
    NAV_ITEMS.find((i) => (i.end ? location.pathname === i.to : location.pathname.startsWith(i.to)))
      ?.label ?? 'Admin'

  return (
    <div className="tw-admin flex min-h-screen w-full">
      {/* ── Desktop sidebar ──────────────────────────────────────────────── */}
      <aside
        className={cn(
          'sticky top-0 hidden h-screen shrink-0 flex-col bg-sidebar transition-[width] duration-200 md:flex',
          collapsed ? 'w-14' : 'w-60',
        )}
      >
        <SidebarHeader brand={brand} role={role} collapsed={collapsed} />
        <Separator className="mb-2 bg-sidebar-border" />
        <nav className="flex-1 overflow-y-auto" aria-label="Admin navigation">
          <SidebarNav collapsed={collapsed} />
        </nav>
      </aside>

      {/* ── Mobile drawer ────────────────────────────────────────────────── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-sidebar transition-transform duration-200 md:hidden',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
        aria-hidden={!mobileOpen}
      >
        <div className="flex items-start justify-between">
          <SidebarHeader brand={brand} role={role} collapsed={false} />
          <Button
            variant="ghost"
            size="icon"
            className="m-2 text-sidebar-foreground hover:bg-sidebar-accent hover:text-white"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
          >
            <X />
          </Button>
        </div>
        <Separator className="mb-2 bg-sidebar-border" />
        <nav className="flex-1 overflow-y-auto" aria-label="Admin navigation">
          <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
        </nav>
      </aside>

      {/* ── Main column ──────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
          {/* Desktop: collapse toggle. Mobile: drawer toggle. */}
          <Button
            variant="ghost"
            size="icon"
            className="hidden md:inline-flex"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <PanelLeft />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            aria-expanded={mobileOpen}
          >
            <PanelLeft />
          </Button>
          <Separator orientation="vertical" className="h-5" />
          <nav aria-label="Breadcrumb" className="min-w-0">
            <ol className="flex items-center gap-1.5 text-sm">
              <li className="hidden text-muted-foreground sm:block">{brand}</li>
              <li className="hidden text-muted-foreground sm:block" aria-hidden>/</li>
              <li className="truncate font-medium text-foreground" aria-current="page">{current}</li>
            </ol>
          </nav>

          <div className="ml-auto">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-10 gap-2 px-2" aria-label="Account menu">
                  <Avatar className="h-7 w-7">
                    <AvatarFallback>{initial}</AvatarFallback>
                  </Avatar>
                  <span className="hidden max-w-[10rem] truncate text-sm font-medium sm:block">
                    {userName}
                  </span>
                  <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuLabel className="flex flex-col">
                  <span className="truncate">{userName}</span>
                  <span className="text-xs font-normal text-muted-foreground">{role}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={onLogout}>
                  <LogOut aria-hidden />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="min-w-0 flex-1 overflow-y-auto text-[0.8125rem]">{children}</main>
      </div>
    </div>
  )
}
