import { useEffect, useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import { useGetMeQuery } from '@/features/auth/authApi'
import { useStaffAlerts } from '@/lib/useStaffAlerts'
import StaffToasts from '@/components/staff/StaffToasts'
import PrintController from '@/features/printing/PrintController'
import LogoutIcon from '@/components/common/LogoutIcon'
import styles from './StaffLayout.module.css'

const NAV_BY_ROLE: Record<string, { to: string; label: string; end?: boolean }[]> = {
  KITCHEN: [{ to: '/kitchen', label: '🍳 Kitchen Queue' }],
  WAITER: [
    { to: '/waiter', label: '🍽️ Ready to Serve', end: true },
    { to: '/waiter/orders', label: '🧾 New Orders' },
    { to: '/waiter/billing', label: '💳 Billing' },
  ],
  COUNTER: [
    { to: '/counter', label: '💳 Billing' },
    { to: '/counter/devices', label: '🖨 Devices' },
  ],
  COUNTER_DISPLAY: [
    { to: '/counter-display', label: '📺 Display' },
  ],
  ADMIN: [
    { to: '/kitchen', label: '🍳 Kitchen' },
    { to: '/waiter', label: '🍽️ Waiter' },
    { to: '/counter', label: '💳 Counter' },
    { to: '/admin', label: '⚙️ Admin' },
  ],
}

export default function StaffLayout() {
  const { role, logout } = useAuth()
  const { data: me } = useGetMeQuery()
  const [open, setOpen] = useState(false)
  const { enabled: alertsOn, toggle: toggleAlerts, toasts, dismissToast } = useStaffAlerts()

  // Lock background scroll while the mobile drawer is open.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  const navItems = (role && NAV_BY_ROLE[role]) ?? []
  const brand = me?.restaurant_name ?? '…'
  const displayName = me?.email ? me.email.split('@')[0] : '…'
  const initial = displayName.charAt(0).toUpperCase() || '?'
  // The passive Counter Display board keeps the sidebar collapsed to a hamburger
  // even on desktop, so the board gets the full screen.
  const collapsed = role === 'COUNTER_DISPLAY'

  const bell = (
    <button
      className={`${styles.alertToggle} ${alertsOn ? styles.alertOn : styles.alertOff}`}
      onClick={toggleAlerts}
      aria-label={alertsOn ? 'Sound alerts on — tap to mute' : 'Sound alerts off — tap to enable'}
      title={alertsOn ? 'Sound alerts: ON (tap to mute)' : 'Sound alerts: OFF (tap to enable)'}
    >
      {alertsOn ? '🔔' : '🔕'}
    </button>
  )

  return (
    <div className={`${styles.root} ${collapsed ? styles.collapsed : ''} ${open ? styles.open : ''}`}>
      <header className={styles.topbar}>
        <button
          className={styles.hamburger}
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
        >
          ☰
        </button>
        <span className={styles.topbarBrand}>{brand}</span>
        {bell}
      </header>

      {open && <div className={styles.backdrop} onClick={() => setOpen(false)} />}

      <nav className={`${styles.nav} ${open ? styles.navOpen : ''}`}>
        <div className={styles.navTop}>
          <div className={styles.navHeader}>
            <div>
              <div className={styles.brand}>{brand}</div>
              <div className={styles.roleChip}>{role}</div>
            </div>
            <button
              className={styles.closeBtn}
              onClick={() => setOpen(false)}
              aria-label="Close menu"
            >
              ×
            </button>
          </div>
          <ul className={styles.navList}>
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        <div className={styles.userFooter}>
          <div className={styles.user}>
            <div className={styles.avatar}>{initial}</div>
            <span className={styles.userName} title={displayName}>{displayName}</span>
          </div>
          {bell}
          <button
            className={styles.logoutBtn}
            onClick={() => void logout()}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogoutIcon />
          </button>
        </div>
      </nav>

      <main className={styles.main}>
        <Outlet />
      </main>

      <StaffToasts toasts={toasts} onDismiss={dismissToast} />
      {(role === 'COUNTER' || role === 'ADMIN') && <PrintController />}
    </div>
  )
}
