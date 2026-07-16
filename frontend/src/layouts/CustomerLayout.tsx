import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useSession } from '@/features/session/useSession'
import { useCallWaiterMutation } from '@/features/session/sessionApi'
import { useCart } from '@/features/cart/useCart'
import { useTheme } from '@/features/ui/useTheme'
import { formatPrice } from '@/lib/currency'
import styles from './CustomerLayout.module.css'

const CURRENCY = 'NPR'

export default function CustomerLayout() {
  const { restaurantName, tableName, invalidate, isInvalidating } = useSession()
  const { totalItems, estimatedTotal } = useCart()
  const { theme } = useTheme()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [callWaiter, { isLoading: isCalling }] = useCallWaiterMutation()
  const [waiterCooldown, setWaiterCooldown] = useState(false)
  const [waiterNotified, setWaiterNotified] = useState(false)
  const [ringing, setRinging] = useState(false)

  const showCartBar = totalItems > 0 && pathname === '/menu'

  async function handleCallWaiter() {
    if (isCalling || waiterCooldown) return
    setRinging(true)
    setTimeout(() => setRinging(false), 600)
    try {
      await callWaiter().unwrap()
      setWaiterNotified(true)
      setTimeout(() => setWaiterNotified(false), 3000)
      // Per-device cooldown to prevent accidental spam (the real anti-spam guard).
      setWaiterCooldown(true)
      setTimeout(() => setWaiterCooldown(false), 5_000)
    } catch {
      // best-effort signal; nothing to surface
    }
  }

  async function handleEndSession() {
    setDrawerOpen(false)
    try {
      await invalidate().unwrap()
    } catch {
      /* invalidate clears local session regardless */
    }
    navigate('/scan', { replace: true })
  }

  return (
    <div className={styles.root} data-theme={theme}>
      {/* ── Top app bar (fixed) ─────────────────────────────────────────── */}
      <header className={styles.appbar}>
        <button
          className={styles.iconBtn}
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
        >
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
            strokeWidth={1.8} strokeLinecap="round" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>

        <button className={styles.brand} onClick={() => navigate('/menu')} aria-label="Go to home">
          REVA
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
            strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={styles.brandWave} aria-hidden="true">
            <circle cx="5" cy="12" r="1.6" fill="currentColor" stroke="none" />
            <path d="M9 8.5a5 5 0 0 1 0 7" />
            <path d="M12.5 5.5a10 10 0 0 1 0 13" />
          </svg>
        </button>

        <div className={styles.appbarRight}>
          <button
            className={`${styles.iconBtn} ${ringing ? styles.callRinging : ''}`}
            onClick={() => void handleCallWaiter()}
            disabled={isCalling || waiterCooldown}
            aria-label={waiterCooldown ? 'Waiter notified' : 'Call waiter'}
            title={waiterCooldown ? 'Waiter notified' : 'Call waiter'}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
              strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="7.5" r="3" />
              <path d="M6.5 19a5.5 5.5 0 0 1 11 0" />
              <path className={styles.vibLeft} d="M4 6a5 5 0 0 0 0 7" />
              <path className={styles.vibRight} d="M20 6a5 5 0 0 1 0 7" />
            </svg>
          </button>

          <button
            className={styles.iconBtn}
            onClick={() => navigate('/cart')}
            aria-label={`Cart${totalItems > 0 ? ` — ${totalItems} items` : ''}`}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
              strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 5h2l1.5 11h10L19 8H7" />
              <circle cx="9" cy="20" r="1.3" />
              <circle cx="17" cy="20" r="1.3" />
            </svg>
            {totalItems > 0 && <span className={styles.appbarBadge}>{totalItems}</span>}
          </button>
        </div>
      </header>

      {waiterNotified && (
        <div className={styles.waiterToast} role="status">Waiter notified ✓</div>
      )}

      <main className={styles.main}>
        <Outlet />
      </main>

      {/* ── Floating "view cart" bar (menu browsing only) ───────────────── */}
      {showCartBar && (
        <button
          className={styles.cartBar}
          onClick={() => navigate('/cart')}
          aria-label={`View cart — ${totalItems} items`}
        >
          <span className={styles.cartCount}>{totalItems}</span>
          <span className={styles.cartLabel}>View Cart</span>
          <span className={styles.cartTotal}>{formatPrice(estimatedTotal, CURRENCY)}</span>
        </button>
      )}

      {/* ── Side drawer (full-screen on mobile, side panel on tablet) ───── */}
      {drawerOpen && (
        <div className={styles.drawerOverlay} onClick={() => setDrawerOpen(false)}>
          <aside
            className={styles.drawer}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="Session menu"
          >
            <div className={styles.drawerHead}>
              <span className={styles.drawerRestaurant}>{restaurantName ?? 'Welcome'}</span>
              {tableName && <span className={styles.drawerTable}>Table: {tableName}</span>}
            </div>

            <nav className={styles.drawerLinks}>
              <button onClick={() => { setDrawerOpen(false); navigate('/menu') }}>Menu</button>
              <button onClick={() => { setDrawerOpen(false); navigate('/order-status') }}>My Orders</button>
              <button onClick={() => { setDrawerOpen(false); navigate('/cart') }}>Cart</button>
            </nav>

            <button
              className={styles.endBtn}
              onClick={() => void handleEndSession()}
              disabled={isInvalidating}
            >
              {isInvalidating ? 'Ending…' : 'End session'}
            </button>
            <button className={styles.drawerClose} onClick={() => setDrawerOpen(false)}>
              Close
            </button>
          </aside>
        </div>
      )}
    </div>
  )
}
