/**
 * Currency display helpers for the customer surface.
 *
 * The backend stores per-restaurant ISO currency codes (e.g. "NPR"). The REVA
 * mockup shows prices as "Rs 220", so we map common codes to a friendlier
 * symbol and fall back to the raw code for anything unmapped.
 */

const SYMBOLS: Record<string, string> = {
  NPR: 'Rs',
  INR: '₹',
  USD: '$',
}

export function currencySymbol(currency: string): string {
  return SYMBOLS[currency.toUpperCase()] ?? currency
}

/** Render an amount in the mockup style, e.g. formatPrice(220, 'NPR') → "Rs 220". */
export function formatPrice(amount: number, currency: string): string {
  const symbol = currencySymbol(currency)
  // Drop trailing ".00" so whole-rupee prices read "Rs 220", keep decimals otherwise.
  const rounded = Math.round(amount * 100) / 100
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2)
  return `${symbol} ${text}`
}
