/**
 * Menu theming — derives a whole small palette from the ONE hex colour an
 * admin picks (admin Settings → "Edit menu"), so accents, dark chrome, and
 * light washes all stay in one family instead of a picked colour clashing
 * with a still-green top bar.
 *
 * Two tiers:
 *  - Tier 1 (dark chrome — the top app bar): computed here in JS, not CSS,
 *    because this is the one surface where an unsafe input (pale yellow,
 *    bright red) must be forced into a safe range. Hue is preserved,
 *    saturation is clamped, and lightness is capped at a fixed dark target
 *    — a bright/pale pick gets pulled down to that target; an already-dark
 *    pick (near-black) is left at or below it, never brightened. The target
 *    itself is theme-aware, matching the two lightnesses the app already
 *    hardcodes for the top bar (~11% light-theme, ~14% dark-theme), so a
 *    picked colour behaves the same way the existing green already does
 *    across the light/dark toggle.
 *  - Tier 2 (light washes — the "Today's Special" background wash and
 *    unselected filter-pill fill): a low-percentage mix of the picked
 *    colour into the theme's actual page-background colour. At that mix
 *    ratio the light-or-dark base dominates, so the result is safe for any
 *    input hue by construction — no HSL clamping needed there.
 *
 * All of it is additive: every consumer reads `var(--menu-x, <existing
 * hardcoded value>)`, so when no accent is picked, none of these custom
 * properties are set and every surface renders exactly as it does today.
 */

import type { CSSProperties } from 'react'

export type MenuThemeMode = 'light' | 'dark'

const HEX_RE = /^#([0-9a-fA-F]{6})$/

// The page background each theme actually resolves --color-bg to (index.css /
// CustomerLayout.module.css's dark-mode override) — the base Tier-2 washes mix into.
const BG_BASE: Record<MenuThemeMode, string> = {
  light: '#faf7f2',
  dark: '#0f1a16',
}

// Matches the app's existing two hardcoded --color-primary-deep values
// (#0f2a21 light / #14342a dark) almost exactly — see menuAccent.test notes.
const DEEP_LIGHTNESS_TARGET: Record<MenuThemeMode, number> = {
  light: 0.112,
  dark: 0.141,
}

function hexToRgb(hex: string): [number, number, number] {
  const match = HEX_RE.exec(hex)
  if (!match) return [0, 0, 0]
  const v = match[1]
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)]
}

function rgbToHex(r: number, g: number, b: number): string {
  const clamp255 = (c: number) => Math.max(0, Math.min(255, Math.round(c)))
  return `#${[r, g, b].map((c) => clamp255(c).toString(16).padStart(2, '0')).join('')}`
}

interface Hsl { h: number; s: number; l: number } // h in [0,360); s,l in [0,1]

function rgbToHsl(r: number, g: number, b: number): Hsl {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return { h: 0, s: 0, l }
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h: number
  switch (max) {
    case r: h = (g - b) / d + (g < b ? 6 : 0); break
    case g: h = (b - r) / d + 2; break
    default: h = (r - g) / d + 4
  }
  return { h: h * 60, s, l }
}

function hue2rgb(p: number, q: number, t: number): number {
  if (t < 0) t += 1
  if (t > 1) t -= 1
  if (t < 1 / 6) return p + (q - p) * 6 * t
  if (t < 1 / 2) return q
  if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
  return p
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  if (s === 0) return [l * 255, l * 255, l * 255]
  const hn = ((h % 360) + 360) % 360 / 360
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [
    hue2rgb(p, q, hn + 1 / 3) * 255,
    hue2rgb(p, q, hn) * 255,
    hue2rgb(p, q, hn - 1 / 3) * 255,
  ]
}

function clamp(x: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, x))
}

function mixHex(a: string, b: string, ratioOfA: number): string {
  const [ar, ag, ab] = hexToRgb(a)
  const [br, bg, bb] = hexToRgb(b)
  return rgbToHex(
    ar * ratioOfA + br * (1 - ratioOfA),
    ag * ratioOfA + bg * (1 - ratioOfA),
    ab * ratioOfA + bb * (1 - ratioOfA),
  )
}

function relativeLuminance(hex: string): number | null {
  const match = HEX_RE.exec(hex)
  if (!match) return null
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(match[1].slice(i, i + 2), 16) / 255)
  const linear = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
}

/** WCAG-ish threshold: computed per-surface, never hardcoded — a light
 *  surface reads better with dark text, a dark one with white. */
function inkFor(hex: string): '#1a1a1a' | '#ffffff' {
  const luminance = relativeLuminance(hex)
  return luminance !== null && luminance > 0.5 ? '#1a1a1a' : '#ffffff'
}

/** Tier 1: a safe dark chrome shade for any input hue. Hue is preserved;
 *  saturation is clamped (or zeroed for an essentially achromatic pick —
 *  no point inventing a hue for a near-gray colour); lightness is capped at
 *  the theme's target so a bright/pale pick is pulled down to it, while an
 *  already-darker pick (near-black) stays at least that dark. */
function deriveSurfaceDeep(accentHex: string, mode: MenuThemeMode): string {
  const { h, s, l } = rgbToHsl(...hexToRgb(accentHex))
  const isAchromatic = s < 0.05
  const sDeep = isAchromatic ? 0 : clamp(s, 0.30, 0.70)
  const lDeep = Math.min(l, DEEP_LIGHTNESS_TARGET[mode])
  return rgbToHex(...hslToRgb(h, sDeep, lDeep))
}

// Price emphasis / category headings use the accent as TEXT directly on
// --color-surface or --color-bg (card/page background) — not as a solid
// block with its own computed ink. That background is near-white in light
// mode and near-black in dark mode, so a near-black accent pick goes
// dark-on-dark in dark mode (and, symmetrically, a very pale pick would go
// light-on-light in light mode) unless the text colour itself is clamped
// into a theme-appropriate contrast range. Bounds found by testing a
// near-black (#1A1A1A) and a pale-yellow (#F5E6A8) pick in both themes.
const ACCENT_TEXT_LIGHTNESS: Record<MenuThemeMode, { min: number; max: number }> = {
  light: { min: 0, max: 0.45 },
  dark: { min: 0.6, max: 1 },
}

/** A contrast-safe variant of the accent for use as TEXT on the page's own
 *  card/background surfaces (never as a solid block — that stays the raw
 *  accent, backed by its own computed ink). */
function deriveAccentText(accentHex: string, mode: MenuThemeMode): string {
  const { h, s, l } = rgbToHsl(...hexToRgb(accentHex))
  const isAchromatic = s < 0.05
  const sText = isAchromatic ? 0 : clamp(s, 0.35, 0.85)
  const { min, max } = ACCENT_TEXT_LIGHTNESS[mode]
  const lText = clamp(l, min, max)
  return rgbToHex(...hslToRgb(h, sText, lText))
}

/** CSS custom properties to set at the customer-surface root. Invalid/missing
 *  colour → empty object, so every consumer's var(--menu-x, <existing>)
 *  fallback resolves to exactly today's hardcoded value — this is what keeps
 *  a restaurant that never picks a colour rendering byte-identically. */
export function deriveMenuTheme(color: string | null | undefined, mode: MenuThemeMode = 'light'): CSSProperties {
  if (!color || !HEX_RE.test(color)) return {}

  const deep = deriveSurfaceDeep(color, mode)
  const bgBase = BG_BASE[mode]
  // "Today's Special" wash mixes the derived deep shade (matching what the
  // hardcoded original mixed in — --color-primary-deep, not the raw accent).
  const bgTint = mixHex(deep, bgBase, 0.08)
  // Filter-pill fill mixes the raw picked colour — chips were never tied to
  // the deep-chrome family, just a light wash of the brand colour itself.
  const tint = mixHex(color, bgBase, 0.16)

  return {
    '--menu-accent': color,
    '--menu-accent-ink': inkFor(color),
    '--menu-accent-text': deriveAccentText(color, mode),
    '--menu-surface-deep': deep,
    '--menu-surface-deep-ink': inkFor(deep),
    '--menu-surface-bg-tint': bgTint,
    '--menu-tint': tint,
    '--menu-tint-ink': inkFor(tint),
  } as CSSProperties
}
