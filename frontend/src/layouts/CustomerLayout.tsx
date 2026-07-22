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
  const [waiterFailed, setWaiterFailed] = useState(false)
  const [ringing, setRinging] = useState(false)

  const showCartBar = totalItems > 0 && pathname === '/menu'

  async function handleCallWaiter() {
    if (isCalling || waiterCooldown) return
    setWaiterFailed(false)
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
      // Never fail silently — the customer must know the waiter was NOT called.
      // No cooldown here, so they can retry immediately.
      setWaiterFailed(true)
      setTimeout(() => setWaiterFailed(false), 5000)
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

        {/* Wordmark only. The signal-wave glyph that used to sit here was pure
            decoration on the home button, but customers read it as "call for
            service" and tapped it expecting a waiter — a false affordance that
            competed with the real Call Waiter action. Removed deliberately. */}
        <button className={styles.brand} onClick={() => navigate('/menu')} aria-label="Go to home">
          REVA
        </button>

        <div className={styles.appbarRight}>
          {/* Labeled action — an unlabeled icon read as decoration, so the word
              "Call Waiter" carries the affordance and the bell reinforces it. */}
          <button
            className={`${styles.callBtn} ${ringing ? styles.callRinging : ''}`}
            onClick={() => void handleCallWaiter()}
            disabled={isCalling || waiterCooldown}
            aria-label={waiterCooldown ? 'Waiter notified' : 'Call waiter'}
          >
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
              strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {/* Service bell — reads as "call for service" far better than a signal wave. */}
              <path d="M18 16H6a6 6 0 0 1 12 0Z" />
              <path d="M4 19h16" />
              <path d="M12 7v3" />
              <circle cx="12" cy="5.6" r="1.3" />
            </svg>
            <span className={styles.callBtnLabel}>
              {isCalling ? 'Calling…' : waiterCooldown ? 'Notified ✓' : 'Call Waiter'}
            </span>
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
        <div className={styles.waiterToast} role="status">Waiter is on the way ✓</div>
      )}

      {waiterFailed && (
        <div className={styles.waiterToastError} role="alert">
          Couldn't reach a waiter — please tap again
        </div>
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
