import { useEffect, useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import LogoutIcon from '@/components/common/LogoutIcon'
import styles from './SuperadminLayout.module.css'

const NAV_ITEMS = [
  { to: '/superadmin', label: '🏢 Restaurants', end: true },
]

export default function SuperadminLayout() {
  const { logout } = useAuth()
  const [open, setOpen] = useState(false)

  // Lock background scroll while the mobile drawer is open.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  return (
    <div className={styles.root}>
      <header className={styles.topbar}>
        <button
          className={styles.hamburger}
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
        >
          ☰
        </button>
        <span className={styles.topbarBrand}>Platform Admin</span>
      </header>

      {open && <div className={styles.backdrop} onClick={() => setOpen(false)} />}

      <nav className={`${styles.nav} ${open ? styles.navOpen : ''}`}>
        <div className={styles.navTop}>
          <div className={styles.navHeader}>
            <div>
              <div className={styles.brand}>Platform Admin</div>
              <div className={styles.roleChip}>SUPERADMIN</div>
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
            <div className={styles.avatar}>S</div>
            <span className={styles.userName}>Superadmin</span>
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
