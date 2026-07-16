/**
 * CategoryIcon — maps a category name keyword to a hand-coded line icon.
 *
 * The backend categories carry only a name (no icon), so we infer an icon from
 * keywords in the name and fall back to a generic cloche. All icons use
 * `currentColor` so the parent controls active/inactive colour.
 */
import type { ReactNode } from 'react'

type IconKey =
  | 'all'
  | 'starter'
  | 'momo'
  | 'main'
  | 'burger'
  | 'pizza'
  | 'noodle'
  | 'drink'
  | 'dessert'
  | 'default'

const KEYWORDS: [RegExp, IconKey][] = [
  [/momo|dumpling/i, 'momo'],
  [/burger/i, 'burger'],
  [/pizza/i, 'pizza'],
  [/noodle|chowmein|chow ?mein|pasta|thukpa/i, 'noodle'],
  [/drink|beverage|juice|coffee|tea|shake|soda|cocktail/i, 'drink'],
  [/dessert|sweet|cake|ice ?cream|pastry/i, 'dessert'],
  [/starter|appetiz|snack|side/i, 'starter'],
  [/main|course|entree|entrée|curry|rice|biryani/i, 'main'],
]

function resolveKey(name: string): IconKey {
  for (const [re, key] of KEYWORDS) {
    if (re.test(name)) return key
  }
  return 'default'
}

const PATHS: Record<IconKey, ReactNode> = {
  all: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  starter: (
    <>
      <path d="M4 13h16a8 8 0 0 0-16 0Z" />
      <path d="M3 17h18" />
      <path d="M12 5v3" />
    </>
  ),
  momo: (
    <>
      <path d="M5 16c0-4 3-7 7-7s7 3 7 7" />
      <path d="M5 16h14l-1.5 2.5h-11Z" />
      <path d="M9 13c1-1 5-1 6 0" />
    </>
  ),
  main: (
    <>
      <path d="M12 6a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7Z" />
      <path d="M4 16h16" />
      <path d="M12 3v3" />
    </>
  ),
  burger: (
    <>
      <path d="M4 9a8 8 0 0 1 16 0Z" />
      <path d="M4 13h16" />
      <path d="M5 16h14a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3Z" />
    </>
  ),
  pizza: (
    <>
      <path d="M12 4 21 19a30 30 0 0 1-18 0Z" />
      <circle cx="10" cy="12" r="1" />
      <circle cx="13.5" cy="15" r="1" />
    </>
  ),
  noodle: (
    <>
      <path d="M5 11h14" />
      <path d="M6 11c0 5 2.5 8 6 8s6-3 6-8" />
      <path d="M9 5l2 6M14 4l1 7" />
    </>
  ),
  drink: (
    <>
      <path d="M7 4h10l-1.2 14a2 2 0 0 1-2 1.8h-3.6a2 2 0 0 1-2-1.8Z" />
      <path d="M7.4 9h9.2" />
    </>
  ),
  dessert: (
    <>
      <path d="M5 21h14l-1.5-9h-11Z" />
      <path d="M6.5 12a5.5 5.5 0 0 1 11 0" />
      <path d="M12 6.5V4" />
      <circle cx="12" cy="3.5" r="0.6" fill="currentColor" />
    </>
  ),
  default: (
    <>
      <path d="M12 4a8 8 0 0 0-8 8h16a8 8 0 0 0-8-8Z" />
      <path d="M3 15h18" />
      <path d="M12 12v9" />
    </>
  ),
}

interface Props {
  name: string
  /** When true, render the "all" grid icon regardless of the name. */
  all?: boolean
  size?: number
}

export default function CategoryIcon({ name, all, size = 24 }: Props) {
  const key = all ? 'all' : resolveKey(name)
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[key]}
    </svg>
  )
}
