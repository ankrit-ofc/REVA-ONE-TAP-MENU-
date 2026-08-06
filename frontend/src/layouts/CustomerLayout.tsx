import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Info } from 'lucide-react'
import { useSession } from '@/features/session/useSession'
import { useCallWaiterMutation } from '@/features/session/sessionApi'
import { useCart } from '@/features/cart/useCart'
import { useTheme } from '@/features/ui/useTheme'
import { formatPrice } from '@/lib/currency'
import { deriveMenuTheme } from '@/lib/menuAccent'
import styles from './CustomerLayout.module.css'

const CURRENCY = 'NPR'
const ABOUT_URL = 'https://revatap.com/'

type CapabilityLine = { emoji: string; text: string }

/** Only list capabilities this restaurant has enabled (missing flag → on). */
function revaCapabilities(flags: {
  orderEnabled: boolean
  callWaiterEnabled: boolean
  qrPaymentEnabled: boolean
}): CapabilityLine[] {
  const lines: CapabilityLine[] = [
    { emoji: '🍽️', text: 'View the digital menu' },
  ]
  if (flags.orderEnabled) {
    lines.push(
      { emoji: '🛒', text: 'Order food directly from your phone' },
      { emoji: '➕', text: 'Add more items anytime' },
      { emoji: '📦', text: 'Track your order status' },
      { emoji: '🧾', text: 'View everything ordered on your table' },
    )
  }
  if (flags.callWaiterEnabled) {
    lines.push({ emoji: '🙋', text: 'Call a waiter with one tap' })
  }
  if (flags.qrPaymentEnabled) {
    lines.push({ emoji: '💳', text: 'Request your bill and pay from your phone' })
  }
  return lines
}

export default function CustomerLayout() {
  const {
    restaurantName,
    tableName,
    invalidate,
    isInvalidating,
    orderEnabled,
    callWaiterEnabled,
    qrPaymentEnabled,
    menuAccentColor,
  } = useSession()
  const { totalItems, estimatedTotal } = useCart()
  const { theme } = useTheme()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [infoOpen, setInfoOpen] = useState(false)
  const [callWaiter, { isLoading: isCalling }] = useCallWaiterMutation()
  const [waiterCooldown, setWaiterCooldown] = useState(false)
  const [waiterNotified, setWaiterNotified] = useState(false)
  const [waiterFailed, setWaiterFailed] = useState(false)
  const [ringing, setRinging] = useState(false)

  const capabilityLines = revaCapabilities({
    orderEnabled,
    callWaiterEnabled,
    qrPaymentEnabled,
  })

  const showCartBar = orderEnabled && totalItems > 0 && pathname === '/menu'

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
    <div className={styles.root} data-theme={theme} style={deriveMenuTheme(menuAccentColor, theme)}>
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
          <button
            className={styles.iconBtn}
            onClick={() => setInfoOpen(true)}
            aria-label="What you can do with REVA"
          >
            <Info size={20} strokeWidth={1.8} aria-hidden="true" />
          </button>

          {/* Labeled action — an unlabeled icon read as decoration, so the word
              "Call Waiter" carries the affordance and the bell reinforces it. */}
          {callWaiterEnabled && (
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
          )}

          {orderEnabled && (
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
          )}
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
              <a
                href={ABOUT_URL}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setDrawerOpen(false)}
              >
                About us
              </a>
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

      {/* ── "What you can do with REVA" (feature-flag–aware) ───────────── */}
      {infoOpen && (
        <div
          className={styles.infoOverlay}
          onClick={() => setInfoOpen(false)}
          role="presentation"
        >
          <div
            className={styles.infoPanel}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="reva-capabilities-title"
          >
            <h2 id="reva-capabilities-title" className={styles.infoTitle}>
              What you can do with REVA
            </h2>
            <ul className={styles.infoList}>
              {capabilityLines.map((line) => (
                <li key={line.text}>
                  <span className={styles.infoEmoji} aria-hidden="true">{line.emoji}</span>
                  <span>{line.text}</span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className={styles.infoClose}
              onClick={() => setInfoOpen(false)}
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
