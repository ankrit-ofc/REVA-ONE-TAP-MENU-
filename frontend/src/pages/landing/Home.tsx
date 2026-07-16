import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Counter from './Counter'
import ExpandRow from './ExpandRow'
import type { ExpandPanel } from './ExpandRow'
import ScrambleAmount from './ScrambleAmount'
import {
  NfcWavesIcon, ArIcon, CheckIcon, SearchIcon, QrIcon, CartIcon, WaiterIcon,
  ChartIcon, BoltIcon, PrintCostIcon, ClockIcon, StarIcon, HeartIcon, RepeatIcon,
  GearIcon, ChevronDownIcon,
} from './icons'

const DEMO_MAILTO = 'mailto:hello@revatap.com?subject=REVA%20TAP%20demo%20request'

const FEATURE_PANELS: ExpandPanel[] = [
  { icon: NfcWavesIcon, title: 'NFC Menu', body: 'Customers tap the REVA stand and the menu opens instantly. No typing, no scanning, no friction.', image: 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=900&q=80' },
  { icon: QrIcon, title: 'QR Menu', body: 'A beautiful QR fallback that works on every phone ever made — iPhone, Android, everything.', image: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=900&q=80' },
  { icon: ArIcon, title: 'AR Menu', body: 'Let guests preview dishes in 3D on their table before they order — see the portion, plating and size in augmented reality.', image: 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=900&q=80' },
  { icon: CartIcon, title: 'Direct Ordering', body: 'Customers order straight from their phone. Orders flow into your system without a single wave for a waiter.', image: 'https://images.unsplash.com/photo-1552566626-52f8b828add9?auto=format&fit=crop&w=900&q=80' },
  { icon: WaiterIcon, title: 'Waiter Dashboard', body: 'Waiters see every table, every order, every status — served faster with zero confusion.', image: 'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=900&q=80' },
]

const BENEFIT_PANELS: ExpandPanel[] = [
  { icon: PrintCostIcon, title: 'Save Printing Costs', body: 'Never reprint a menu again. Update digitally, forever.' },
  { icon: ChartIcon, title: 'Increase Sales', body: 'Photos and videos sell more. Upsells happen automatically.' },
  { icon: BoltIcon, title: 'Faster Ordering', body: 'Orders reach the kitchen in seconds, not minutes.' },
  { icon: ClockIcon, title: 'Reduce Wait Time', body: 'No waiting for menus, no waving for waiters.' },
  { icon: StarIcon, title: 'Modern Experience', body: 'Feel like the most forward-thinking place on the street.' },
  { icon: HeartIcon, title: 'Happier Customers', body: 'Smooth, beautiful, in their language. They notice.' },
  { icon: RepeatIcon, title: 'More Repeat Visits', body: 'Great experiences bring people — and their friends — back.' },
  { icon: GearIcon, title: 'Easy Management', body: 'One dashboard runs your whole menu operation.' },
]

const STEPS: { title: string; body: string }[] = [
  { title: 'Tap NFC or Scan QR', body: 'Customer taps the REVA stand or scans the QR code on the table.' },
  { title: 'Menu Opens Instantly', body: 'Your full digital menu appears in their browser — no app, no signup, no waiting.' },
  { title: 'Browse Food', body: "Photos, videos, descriptions and prices in the customer's own language." },
  { title: 'Place Order', body: 'Customer builds a cart and orders directly from their seat.' },
  { title: 'Kitchen Receives Order', body: 'The KOT hits the kitchen screen instantly, color-coded by priority.' },
  { title: 'Food Delivered', body: "Waiters get notified the moment it's ready. Hot food, happy guests." },
]

const POPULAR = [
  { emoji: '🥟', name: 'Steam Momo', w: '92%', count: '1,240' },
  { emoji: '🍕', name: 'Margherita Pizza', w: '74%', count: '986' },
  { emoji: '🍔', name: 'Classic Burger', w: '61%', count: '812' },
  { emoji: '☕', name: 'Cappuccino', w: '48%', count: '644' },
  { emoji: '🍰', name: 'Chocolate Cake', w: '35%', count: '470' },
]

interface MqCard { initials: string; avatar: string; name: string; role: string; quote: string }
const T = {
  rs: { initials: 'RS', avatar: 'linear-gradient(135deg,#0E6B4D,#16A34A)', name: 'Rajesh Shrestha', role: 'Owner, Everest Bistro', quote: 'We removed paper menus in one weekend. Table turnover went up 30% in the first month.' },
  sr: { initials: 'SR', avatar: 'linear-gradient(135deg,#0d9488,#22d3ee)', name: 'Sita Rai', role: 'Owner, Momo Ghar', quote: 'Orders hit the kitchen instantly — no more lost tickets on a busy night.' },
  pg: { initials: 'PG', avatar: 'linear-gradient(135deg,#F59E0B,#EF4444)', name: 'Priya Gurung', role: 'Manager, Café Kathmandu', quote: 'Photos sell the dish for us. Printing costs are gone and specials go live in seconds.' },
  bl: { initials: 'BL', avatar: 'linear-gradient(135deg,#e11d48,#fb923c)', name: 'Bikash Lama', role: 'Manager, Pokhara Grill', quote: 'Turnover is up, staff stress is down. Guests love ordering right from their seat.' },
  at: { initials: 'AT', avatar: 'linear-gradient(135deg,#6366F1,#8B5CF6)', name: 'Anil Thapa', role: 'Owner, The Terrace Resort', quote: 'Tourists finally read our menu in their own language. Zero missed orders since we started.' },
  ds: { initials: 'DS', avatar: 'linear-gradient(135deg,#2563eb,#38bdf8)', name: 'Deepa Shah', role: 'Owner, Newari Kitchen', quote: 'Setup took one afternoon. Updating prices now takes seconds, not a reprint.' },
} satisfies Record<string, MqCard>

const MQ_COLS: { dur: string; rev: boolean; cards: MqCard[] }[] = [
  { dur: '34s', rev: false, cards: [T.rs, T.sr, T.pg] },
  { dur: '40s', rev: true, cards: [T.bl, T.at, T.ds] },
  { dur: '30s', rev: false, cards: [T.pg, T.ds, T.sr] },
]

const PLANS = [
  {
    name: 'STARTER', featured: false, desc: 'For cafés and small restaurants getting started',
    monthly: '1,999', yearly: '1,599', priceSuffix: '/month', cta: 'Start Free Trial', ctaClass: 'btn-secondary',
    features: ['QR digital menu', 'Up to 50 menu items', 'Food images', 'Live menu updates', 'Basic analytics'],
  },
  {
    name: 'PROFESSIONAL', featured: true, desc: 'For busy restaurants that want the full experience',
    monthly: '4,999', yearly: '3,999', priceSuffix: '/month', cta: 'Start Free Trial', ctaClass: 'btn-primary',
    features: ['Everything in Starter', 'NFC stands included', 'Video menu & unlimited items', 'Direct ordering + waiter & kitchen dashboards', 'Multi-language menus', 'Advanced analytics'],
  },
  {
    name: 'ENTERPRISE', featured: false, desc: 'For hotels, chains, resorts and food courts',
    monthly: 'Custom', yearly: 'Custom', priceSuffix: ' pricing', cta: 'Talk to Sales', ctaClass: 'btn-secondary',
    features: ['Everything in Professional', 'Multiple locations & outlets', 'Custom branding & domain', 'POS integrations & API', 'Dedicated success manager'],
  },
]

const FAQS = [
  { q: 'Do customers need to install an app?', a: "No. Everything runs in the phone's browser. Customers tap the NFC stand or scan the QR code and the menu opens instantly — no download, no signup, no account." },
  { q: 'Can I update my menu anytime?', a: 'Yes. Change prices, add specials, hide sold-out items — every change goes live on all tables the moment you save it.' },
  { q: 'Does it work on iPhone and Android?', a: 'Yes, both. NFC tap works on all modern iPhones and Android phones, and the QR code works on literally every phone with a camera.' },
  { q: 'Can I use QR only, without NFC?', a: 'Yes. You can run QR-only, NFC-only, or both together. Most restaurants use both — NFC on the stands, QR printed as a backup.' },
  { q: 'How long does setup take?', a: "Most restaurants are live within a day. Upload your menu, place the stands on tables, and you're serving digitally. Our team helps with onboarding on every plan." },
  { q: 'What happens if the internet goes down?', a: "Menus stay cached on customers' phones, and the dashboard reconnects automatically. Orders queue locally and sync the moment you're back online." },
]

const FOODS = [
  { cls: 'f-tl', emoji: '🥟', rot: -16 },
  { cls: 'f-tr', emoji: '🍕', rot: 15 },
  { cls: 'f-ml', emoji: '🍔', rot: -11 },
  { cls: 'f-mr', emoji: '🍜', rot: 18 },
  { cls: 'f-bc', emoji: '🍰', rot: 9 },
]

function MqCardView({ c }: { c: MqCard }) {
  return (
    <article className="mq-card">
      <div className="mq-top">
        <div className="mq-av" style={{ background: c.avatar }}>{c.initials}</div>
        <div>
          <div className="mq-name">{c.name}</div>
          <div className="mq-role">{c.role}</div>
        </div>
      </div>
      <div className="mq-stars">★★★★★</div>
      <p className="mq-quote">“{c.quote}”</p>
    </article>
  )
}

export default function LandingHome() {
  const rootRef = useRef<HTMLDivElement>(null)
  const [yearly, setYearly] = useState(false)
  const [openFaq, setOpenFaq] = useState<number | null>(0)

  // Scroll-reveal: reveal each `.reveal` element the first time it enters view.
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const els = Array.from(root.querySelectorAll<HTMLElement>('.reveal'))
    if (typeof IntersectionObserver === 'undefined') {
      els.forEach((el) => el.classList.add('visible'))
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('visible')
            io.unobserve(e.target)
          }
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
    )
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  // Hero: emoji food rests at the display edges, then merges into the phone as
  // you scroll; plus a subtle parallax on the whole hero visual (desktop only).
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const hero = root.querySelector<HTMLElement>('.hero')
    const phone = root.querySelector<HTMLElement>('.phone')
    const heroVisual = root.querySelector<HTMLElement>('.hero-visual')
    const foods = Array.from(root.querySelectorAll<HTMLElement>('.food'))
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce || !hero || !phone) return

    const COLLECT_DIST = 820
    const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
    const easeOut = (t: number) => 1 - Math.pow(1 - t, 2)
    const wide = matchMedia('(min-width: 1020px)')
    let ticking = false

    const update = () => {
      ticking = false
      const p = clamp01(window.scrollY / COLLECT_DIST)
      const heroRect = hero.getBoundingClientRect()
      const pRect = phone.getBoundingClientRect()
      const phoneCx = pRect.left + pRect.width / 2 - heroRect.left
      const phoneCy = pRect.top + pRect.height / 2 - heroRect.top
      foods.forEach((f, i) => {
        const lag = (i % 5) * 0.06
        const pi = easeOut(clamp01((p - lag) / (1 - lag)))
        const fCx = f.offsetLeft + f.offsetWidth / 2
        const fCy = f.offsetTop + f.offsetHeight / 2
        const dx = (phoneCx - fCx) * pi
        const dy = (phoneCy - fCy) * pi
        const scale = 1 - 0.78 * pi
        const rot = (Number(f.dataset.rot) || 0) * (1 - pi)
        f.style.transform = `translate(${dx}px, ${dy}px) scale(${scale}) rotate(${rot}deg)`
        f.style.opacity = String(clamp01(pi > 0.82 ? (1 - pi) / 0.18 : 1))
      })
      if (heroVisual && wide.matches && window.scrollY < 900) {
        heroVisual.style.transform = `translateY(${window.scrollY * 0.06}px)`
      }
    }

    const onScroll = () => {
      if (!ticking) { ticking = true; requestAnimationFrame(update) }
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', update, { passive: true })
    update()
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', update)
    }
  }, [])

  return (
    <div ref={rootRef}>
      {/* ── HERO ─────────────────────────────────────────────────────────── */}
      <header className="hero" id="top">
        <div className="food-burst" aria-hidden="true">
          {FOODS.map((f) => (
            <span key={f.cls} className={`food ${f.cls}`} data-rot={f.rot}>{f.emoji}</span>
          ))}
        </div>
        <div className="container hero-grid">
          <div className="hero-copy">
            <h1 className="fade-up fu-2">
              One Tap.
              <br />
              <span className="grad">Your Menu.</span>
            </h1>
            <p className="hero-sub fade-up fu-3">
              Experience the future of restaurant dining with NFC &amp; QR-powered digital menus
              that open instantly — no app required.
            </p>
            <div className="hero-ctas fade-up fu-4">
              <Link to="/login" className="btn btn-primary">
                Go to App <span className="arrow">→</span>
              </Link>
              <a href={DEMO_MAILTO} className="btn btn-secondary">Book a Demo</a>
            </div>
            <div className="hero-badges fade-up fu-4">
              <span className="hero-badge"><CheckIcon />No app required</span>
              <span className="hero-badge"><CheckIcon />Works on every phone</span>
              <span className="hero-badge"><CheckIcon />Set up in minutes</span>
            </div>
          </div>

          <div className="hero-visual">
            <div className="blob blob-1" />
            <div className="blob blob-2" />

            <div className="phone">
              <div className="phone-notch" />
              <div className="phone-screen">
                <div className="ps-head">
                  <div className="ps-rest">Everest Bistro · Table 12</div>
                  <div className="ps-title">Our Menu</div>
                  <div className="ps-search"><SearchIcon style={{ width: 12, height: 12 }} /> Search dishes…</div>
                </div>
                <div className="ps-cats">
                  <span className="ps-cat active">All</span>
                  <span className="ps-cat">Momo</span>
                  <span className="ps-cat">Pizza</span>
                  <span className="ps-cat">Coffee</span>
                  <span className="ps-cat">Desserts</span>
                </div>
                <div className="ps-items">
                  <div className="ps-item">
                    <div className="ps-img" style={{ background: '#FEF3C7' }}>🥟</div>
                    <div className="ps-info">
                      <div className="ps-name">Steam Momo</div>
                      <div className="ps-desc">Juicy chicken dumplings, house chutney</div>
                      <div className="ps-row"><span className="ps-price">Rs. 220</span><span className="ps-rate">★ 4.9</span></div>
                    </div>
                    <div className="ps-add">+</div>
                  </div>
                  <div className="ps-item">
                    <div className="ps-img" style={{ background: '#FEE2E2' }}>🍕</div>
                    <div className="ps-info">
                      <div className="ps-name">Margherita Pizza</div>
                      <div className="ps-desc">Wood-fired, fresh basil &amp; mozzarella</div>
                      <div className="ps-row"><span className="ps-price">Rs. 540</span><span className="ps-rate">★ 4.8</span></div>
                    </div>
                    <div className="ps-add">+</div>
                  </div>
                  <div className="ps-item">
                    <div className="ps-img" style={{ background: '#E0F2FE' }}>🍔</div>
                    <div className="ps-info">
                      <div className="ps-name">Classic Burger</div>
                      <div className="ps-desc">Smashed patty, cheddar, secret sauce</div>
                      <div className="ps-row"><span className="ps-price">Rs. 380</span><span className="ps-rate">★ 4.7</span></div>
                    </div>
                    <div className="ps-add">+</div>
                  </div>
                </div>
                <div className="ps-cart"><span>🛒 3 items · Rs. 1,140</span><span>Checkout</span></div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── TRUSTED BY ───────────────────────────────────────────────────── */}
      <section className="trusted">
        <div className="container">
          <div className="trusted-label reveal">
            Trusted by <strong>100+ restaurants</strong> across the region
          </div>
          <div className="logo-row reveal reveal-d1">
            <span className="t-logo">◆ Everest Bistro</span>
            <span className="t-logo">✦ Café Kathmandu</span>
            <span className="t-logo">▲ The Terrace</span>
            <span className="t-logo">◇ Himalayan Java</span>
            <span className="t-logo">★ Roadhouse</span>
            <span className="t-logo">● Fire &amp; Ice</span>
          </div>
        </div>
      </section>

      {/* ── FEATURES (expand panels) ─────────────────────────────────────── */}
      <section className="section-pad" id="features">
        <div className="container">
          <div className="center reveal">
            <div className="eyebrow">Features</div>
            <h2 className="section-title">
              Everything your restaurant needs.
              <br />
              Nothing it doesn't.
            </h2>
          </div>
          <ExpandRow panels={FEATURE_PANELS} />
        </div>
      </section>

      {/* ── HOW IT WORKS ─────────────────────────────────────────────────── */}
      <section className="section-pad hiw" id="how">
        <div className="container">
          <div className="center reveal">
            <div className="eyebrow">How It Works</div>
            <h2 className="section-title">From tap to table in six steps</h2>
            <p className="section-sub">
              A dining flow so smooth, your customers will think about it — and come back for it.
            </p>
          </div>
          <div className="timeline">
            {STEPS.map((s, i) => (
              <div className="step reveal" key={s.title}>
                <div className="step-num">{String(i + 1).padStart(2, '0')}</div>
                <div className="step-body">
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── BENEFITS (green expand panels) ───────────────────────────────── */}
      <section className="section-pad" style={{ paddingTop: 20 }}>
        <div className="benefits-band">
          <div className="container" style={{ paddingTop: 100, paddingBottom: 100 }}>
            <div className="center reveal">
              <div className="eyebrow">Why REVA</div>
              <h2 className="section-title">The upgrade your restaurant feels on day one</h2>
              <p className="section-sub">Less friction for guests. More margin for you.</p>
            </div>
            <ExpandRow panels={BENEFIT_PANELS} onGreen />
          </div>
        </div>
      </section>

      {/* ── ANALYTICS ────────────────────────────────────────────────────── */}
      <section className="section-pad">
        <div className="container">
          <div className="center reveal">
            <div className="eyebrow">Analytics</div>
            <h2 className="section-title">Know exactly what's working</h2>
            <p className="section-sub">
              Orders, revenue, visitors, peak hours and your best-selling dishes — beautifully
              visualized.
            </p>
          </div>
          <div className="stats-row">
            <div className="stat reveal"><div className="stat-value"><Counter to={100} suffix="+" /></div><div className="stat-label">Restaurants Onboard</div></div>
            <div className="stat reveal reveal-d1"><div className="stat-value"><Counter to={250} suffix="K+" /></div><div className="stat-label">Orders Processed</div></div>
            <div className="stat reveal reveal-d2"><div className="stat-value"><Counter to={38} suffix="%" /></div><div className="stat-label">Faster Table Turnover</div></div>
            <div className="stat reveal reveal-d3"><div className="stat-value"><Counter to={24} suffix="%" /></div><div className="stat-label">Average Sales Lift</div></div>
          </div>
          <div className="analytics-grid">
            <div className="chart-card reveal">
              <div className="cc-head"><h3>Revenue &amp; Orders</h3><span>Last 30 days</span></div>
              <svg className="line-chart" viewBox="0 0 560 220" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="rtAreaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0E6B4D" stopOpacity=".22" />
                    <stop offset="100%" stopColor="#0E6B4D" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <g stroke="#E2E8F0" strokeWidth="1">
                  <line x1="0" y1="55" x2="560" y2="55" /><line x1="0" y1="110" x2="560" y2="110" /><line x1="0" y1="165" x2="560" y2="165" />
                </g>
                <path className="area" d="M0,180 C40,168 70,150 105,145 C140,140 165,155 200,138 C235,121 260,95 300,98 C340,101 360,120 400,100 C440,80 460,55 505,48 C525,45 545,42 560,38 L560,220 L0,220 Z" />
                <path className="line" d="M0,180 C40,168 70,150 105,145 C140,140 165,155 200,138 C235,121 260,95 300,98 C340,101 360,120 400,100 C440,80 460,55 505,48 C525,45 545,42 560,38" />
                <circle cx="505" cy="48" r="6" fill="#0E6B4D" />
                <circle cx="505" cy="48" r="11" fill="#0E6B4D" opacity=".15" />
              </svg>
              <div style={{ display: 'flex', gap: 24, marginTop: 18 }}>
                <span style={{ fontSize: 13, color: 'var(--gray)', display: 'flex', alignItems: 'center', gap: 7 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--green)', display: 'inline-block' }} />Revenue · <strong style={{ color: 'var(--dark)' }}>Rs. 21.4L</strong></span>
                <span style={{ fontSize: 13, color: 'var(--gray)', display: 'flex', alignItems: 'center', gap: 7 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--accent)', opacity: 0.5, display: 'inline-block' }} />Peak hour · <strong style={{ color: 'var(--dark)' }}>7–9 PM</strong></span>
              </div>
            </div>
            <div className="chart-card reveal reveal-d1">
              <div className="cc-head"><h3>Popular Items</h3><span>This week</span></div>
              {POPULAR.map((p) => (
                <div className="pop-item" key={p.name}>
                  <div className="pop-emoji">{p.emoji}</div>
                  <div className="pop-info">
                    <div className="pop-name">{p.name}</div>
                    <div className="pop-bar"><i style={{ ['--w' as string]: p.w } as React.CSSProperties} /></div>
                  </div>
                  <div className="pop-count">{p.count}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── TESTIMONIALS (3D marquee) ────────────────────────────────────── */}
      <section className="section-pad" style={{ paddingTop: 30 }}>
        <div className="container">
          <div className="center reveal">
            <div className="eyebrow">Testimonials</div>
            <h2 className="section-title">Loved by restaurant owners</h2>
            <p className="section-sub">From cafés to fine dining — here's what happens after the switch.</p>
          </div>
          <div className="testi-3d reveal">
            <div className="testi-3d-stage">
              {MQ_COLS.map((col, ci) => (
                <div className={col.rev ? 'mq-col rev' : 'mq-col'} style={{ ['--dur' as string]: col.dur } as React.CSSProperties} key={ci}>
                  {[...col.cards, ...col.cards].map((c, i) => (
                    <MqCardView c={c} key={`${ci}-${i}`} />
                  ))}
                </div>
              ))}
            </div>
            <div className="fade fade-t" /><div className="fade fade-b" /><div className="fade fade-l" /><div className="fade fade-r" />
          </div>
        </div>
      </section>

      {/* ── PRICING ──────────────────────────────────────────────────────── */}
      <section className="section-pad" id="pricing" style={{ paddingTop: 30 }}>
        <div className="container">
          <div className="center reveal">
            <div className="eyebrow">Pricing</div>
            <h2 className="section-title">Simple pricing that pays for itself</h2>
            <p className="section-sub">Start free for 14 days. No credit card, no setup fees, cancel anytime.</p>
            <div className="toggle-wrap">
              <button className={yearly ? 'toggle-opt' : 'toggle-opt active'} onClick={() => setYearly(false)}>Monthly</button>
              <button className={yearly ? 'toggle-opt active' : 'toggle-opt'} onClick={() => setYearly(true)}>
                Yearly<span className="save-badge">Save 20%</span>
              </button>
            </div>
          </div>
          <div className="pricing-grid">
            {PLANS.map((p) => {
              const isCustom = p.monthly === 'Custom'
              return (
                <div className={p.featured ? 'price-card featured reveal reveal-d1' : 'price-card reveal'} key={p.name}>
                  {p.featured && <div className="pop-badge">Most Popular</div>}
                  <div className="plan-name" style={p.featured ? { color: '#4ADE80' } : undefined}>{p.name}</div>
                  <div className="plan-desc">{p.desc}</div>
                  <div className="plan-price" style={isCustom ? { fontSize: 34, paddingTop: 8 } : undefined}>
                    {!isCustom && 'Rs. '}
                    {isCustom
                      ? <span className="amount">Custom</span>
                      : <ScrambleAmount monthly={p.monthly} yearly={p.yearly} isYearly={yearly} />}
                    <small>{p.priceSuffix}</small>
                  </div>
                  <ul className="plan-features">
                    {p.features.map((f) => (
                      <li key={f}><CheckIcon />{f}</li>
                    ))}
                  </ul>
                  <a href={DEMO_MAILTO} className={`btn ${p.ctaClass}`}>{p.cta}</a>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="section-pad" style={{ paddingTop: 30 }}>
        <div className="container">
          <div className="center reveal">
            <div className="eyebrow">FAQ</div>
            <h2 className="section-title">Questions, answered</h2>
          </div>
          <div className="faq-list reveal reveal-d1">
            {FAQS.map((f, i) => (
              <div className={openFaq === i ? 'faq-item open' : 'faq-item'} key={f.q}>
                <button className="faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)} aria-expanded={openFaq === i}>
                  {f.q}
                  <span className="chev"><ChevronDownIcon /></span>
                </button>
                <div className="faq-a">
                  <div><p>{f.a}</p></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Sticky mobile CTA */}
      <div className="sticky-cta">
        <Link to="/login" className="btn btn-primary">Go to App →</Link>
      </div>
    </div>
  )
}
