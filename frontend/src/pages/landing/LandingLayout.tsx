import { useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { LogoWavesIcon, InstagramIcon, LinkedinIcon, FacebookIcon } from './icons'
import './landing.css'

const DEMO_MAILTO = 'mailto:hello@revatap.com?subject=REVA%20TAP%20demo%20request'

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#how', label: 'How it Works' },
  { href: '#pricing', label: 'Pricing' },
  { href: '#contact', label: 'Contact' },
]

/**
 * Public REVA TAP marketing chrome: a fixed nav that condenses into a floating
 * pill on scroll, a hamburger mobile menu, and the footer — wrapped around the
 * single-page <Outlet>. Everything is scoped under `.rt` (see landing.css).
 * The prominent "Go to App" button routes staff to the real product at /login.
 */
const PAGE_TITLE = 'REVA TAP — One Tap. Your Menu.'
const PAGE_DESCRIPTION =
  'Transform your restaurant with NFC & QR-powered digital menus that customers can access instantly. No app required.'

export default function LandingLayout() {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  // SEO head bits: the app has no head manager, so set the marketing title +
  // description while the landing page is mounted and restore on unmount.
  useEffect(() => {
    const prevTitle = document.title
    document.title = PAGE_TITLE
    const existing = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    const created = !existing
    const meta = existing ?? document.createElement('meta')
    if (created) {
      meta.name = 'description'
      document.head.appendChild(meta)
    }
    const prevDescription = meta.content
    meta.content = PAGE_DESCRIPTION
    return () => {
      document.title = prevTitle
      if (created) meta.remove()
      else meta.content = prevDescription
    }
  }, [])

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Smooth-scroll to in-page anchors without a global scroll-behavior rule.
  const jumpTo = (href: string) => (e: React.MouseEvent) => {
    if (!href.startsWith('#')) return
    const el = document.getElementById(href.slice(1))
    if (el) {
      e.preventDefault()
      el.scrollIntoView({ behavior: 'smooth' })
    }
    setMenuOpen(false)
  }

  return (
    <div className="rt">
      <nav className={scrolled ? 'scrolled' : undefined}>
        <div className="nav-inner">
          <Link to="/" className="logo" aria-label="REVA TAP home">
            REVA<span className="logo-waves"><LogoWavesIcon /></span>
          </Link>
          <div className="nav-links">
            {NAV_LINKS.map((l) => (
              <a key={l.href} href={l.href} onClick={jumpTo(l.href)}>
                {l.label}
              </a>
            ))}
          </div>
          <div className="nav-cta">
            <a href={DEMO_MAILTO} className="btn btn-ghost">
              Book Demo
            </a>
            <Link to="/login" className="btn btn-primary" style={{ padding: '11px 24px' }}>
              Get Started
            </Link>
            <button
              className="hamburger"
              aria-label="Menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              <span />
              <span />
              <span />
            </button>
          </div>
        </div>
      </nav>

      <div className={menuOpen ? 'mobile-menu open' : 'mobile-menu'}>
        {NAV_LINKS.map((l) => (
          <a key={l.href} href={l.href} onClick={jumpTo(l.href)}>
            {l.label}
          </a>
        ))}
        <Link to="/login" style={{ color: 'var(--green)' }} onClick={() => setMenuOpen(false)}>
          Get Started →
        </Link>
      </div>

      <main>
        <Outlet />
      </main>

      <footer id="contact">
        <div className="container">
          <div className="footer-grid">
            <div>
              <Link to="/" className="logo">
                REVA<span className="logo-waves"><LogoWavesIcon /></span>
              </Link>
              <p className="footer-tag">
                One Tap. Your Menu. The smart ordering platform for modern restaurants.
              </p>
              <div className="socials">
                <a href="#" aria-label="Instagram"><InstagramIcon /></a>
                <a href="#" aria-label="LinkedIn"><LinkedinIcon /></a>
                <a href="#" aria-label="Facebook"><FacebookIcon /></a>
              </div>
            </div>
            <div className="f-col">
              <h4>Product</h4>
              <a href="#features" onClick={jumpTo('#features')}>Features</a>
              <a href="#how" onClick={jumpTo('#how')}>How it Works</a>
              <a href="#pricing" onClick={jumpTo('#pricing')}>Pricing</a>
              <a href={DEMO_MAILTO}>Book a Demo</a>
            </div>
            <div className="f-col">
              <h4>Company</h4>
              <Link to="/login">Staff Login</Link>
              <a href="#">About</a>
              <a href="#">Careers</a>
              <a href="#">Privacy Policy</a>
              <a href="#">Terms of Service</a>
            </div>
            <div className="f-col">
              <h4>Contact</h4>
              <a href="mailto:hello@revatap.com">hello@revatap.com</a>
              <a href="tel:+9779800000000">+977 980-000-0000</a>
              <a href="#">Support Center</a>
            </div>
          </div>
          <div className="footer-bottom">
            <span>© {new Date().getFullYear()} REVA TAP. All rights reserved.</span>
            <span>Made with care for restaurants everywhere.</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
