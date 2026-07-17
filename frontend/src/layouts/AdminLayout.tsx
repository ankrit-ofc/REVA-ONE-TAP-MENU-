import { useEffect, useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import { useGetMeQuery } from '@/features/auth/authApi'
import LogoutIcon from '@/components/common/LogoutIcon'
import styles from './AdminLayout.module.css'
import '@/styles/admin.css'

const NAV_ITEMS = [
  { to: '/admin', label: '📊 Dashboard', end: true },
  { to: '/admin/categories', label: '📂 Categories' },
  { to: '/admin/products', label: '🍱 Products' },
  { to: '/admin/addons', label: '➕ Add-ons' },
  { to: '/admin/staff', label: '👤 Staff' },
  { to: '/admin/tables', label: '🪑 Tables' },
  { to: '/admin/devices', label: '🖨 Devices' },
  { to: '/admin/settings', label: '⚙️ Settings' },
]

export default function AdminLayout() {
  const { role, logout } = useAuth()
  const { data: me } = useGetMeQuery()
  const [open, setOpen] = useState(false)

  // Lock background scroll while the mobile drawer is open so the page behind
  // it doesn't show its own scrollbar / scroll underneath the overlay.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  const brand = me?.restaurant_name ?? '…'
  const displayName = me?.email ? me.email.split('@')[0] : '…'
  const initial = displayName.charAt(0).toUpperCase() || '?'

  return (
    <div className={styles.root}>
      {/* Mobile top bar — hidden on desktop */}
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
            {NAV_ITEMS.map((item) => (
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
    </div>
  )
}
