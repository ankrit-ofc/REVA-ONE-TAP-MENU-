/* Inline SVG icons for the REVA TAP landing site. Stroke icons share a common
   set of props; each is a small presentational component so the page markup
   stays readable. */
import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>

const stroke = (extra?: P): P => ({
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  ...extra,
})

/** Vertical wave mark that sits after the "REVA" wordmark in the nav/footer. */
export function LogoWavesIcon(props: P) {
  return (
    <svg viewBox="0 0 12 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" {...props}>
      <path d="M2 9.5A2.7 2.7 0 0 1 2 14.5" />
      <path d="M2 6.5A5.7 5.7 0 0 1 2 17.5" />
      <path d="M2 3.5A8.7 8.7 0 0 1 2 20.5" />
    </svg>
  )
}

/** Cube / augmented-reality icon (AR Menu feature). */
export function ArIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M12 2 3 7v10l9 5 9-5V7z" />
      <path d="m3 7 9 5 9-5M12 12v10" />
    </svg>
  )
}

/** The REVA "tap" wifi/NFC mark used in the logo. */
export function MarkIcon(props: P) {
  return (
    <svg {...stroke({ strokeWidth: 2.2 })} {...props}>
      <path d="M12 20v-8" />
      <path d="M8.5 9.5a5 5 0 0 1 7 0" />
      <path d="M5.5 6.5a9.2 9.2 0 0 1 13 0" />
      <circle cx="12" cy="13" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  )
}

/** NFC waves without the centre dot (for the tap stand). */
export function NfcWavesIcon(props: P) {
  return (
    <svg {...stroke({ strokeWidth: 2.2 })} {...props}>
      <path d="M12 20v-8" />
      <path d="M8.5 9.5a5 5 0 0 1 7 0" />
      <path d="M5.5 6.5a9.2 9.2 0 0 1 13 0" />
    </svg>
  )
}

export function CheckIcon(props: P) {
  return (
    <svg {...stroke({ strokeWidth: 2.4 })} {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

export function SearchIcon(props: P) {
  return (
    <svg {...stroke({ strokeWidth: 2.4 })} {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4-4" />
    </svg>
  )
}

export function QrIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <path d="M14 14h3v3h-3zM20 14h1M14 20h1M20 20h1M17 20v1" />
    </svg>
  )
}

export function VideoIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <rect x="2" y="4" width="20" height="16" rx="3" />
      <path d="m10 9 5 3-5 3z" fill="currentColor" />
    </svg>
  )
}

export function ImageIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-4-4-8 8" />
    </svg>
  )
}

export function RefreshIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v6h-6" />
    </svg>
  )
}

export function CartIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <circle cx="9" cy="20" r="1.5" />
      <circle cx="18" cy="20" r="1.5" />
      <path d="M2 3h3l2.6 12.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.6L21 7H6" />
    </svg>
  )
}

export function WaiterIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M19 8v6M22 11h-6" />
    </svg>
  )
}

export function KitchenIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M12 3c-1.5 2-4 3.5-4 6a4 4 0 0 0 8 0c0-2.5-2.5-4-4-6z" />
      <path d="M5 21h14M7 21c0-2.2 2.2-4 5-4s5 1.8 5 4" />
    </svg>
  )
}

export function ChartIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M3 3v18h18" />
      <path d="m7 14 4-4 3 3 5-6" />
    </svg>
  )
}

export function GlobeIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
    </svg>
  )
}

export function PhoneIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <rect x="7" y="2" width="10" height="20" rx="3" />
      <path d="M11 18h2" />
    </svg>
  )
}

export function BoltIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M13 2 3 14h7l-1 8 10-12h-7z" />
    </svg>
  )
}

export function PrintCostIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  )
}

export function ClockIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </svg>
  )
}

export function StarIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M12 2 15 8.5 22 9.3 17 14l1.2 7L12 17.8 5.8 21 7 14 2 9.3 9 8.5z" />
    </svg>
  )
}

export function HeartIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l8.8 8.9 8.8-8.9a5.5 5.5 0 0 0 0-7.8z" />
    </svg>
  )
}

export function RepeatIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M17 2v6M21 6h-8M7 22a5 5 0 0 1-5-5c0-4 3.5-4.5 5-9 1.5 4.5 5 5 5 9a5 5 0 0 1-5 5z" />
    </svg>
  )
}

export function GearIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  )
}

export function ChevronDownIcon(props: P) {
  return (
    <svg {...stroke({ strokeWidth: 2.4 })} {...props}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

export function InstagramIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <rect x="2" y="2" width="20" height="20" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function LinkedinIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect x="2" y="9" width="4" height="12" />
      <circle cx="4" cy="4" r="2" />
    </svg>
  )
}

export function FacebookIcon(props: P) {
  return (
    <svg {...stroke()} {...props}>
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  )
}
