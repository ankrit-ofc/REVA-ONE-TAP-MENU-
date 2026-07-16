/**
 * Client-side menu heuristics.
 *
 * The backend has no popularity/bestseller/featured data, but the REVA mockup
 * shows a "Most Popular" rail and "Bestseller" badges. These pure helpers fake
 * that purely on the frontend (first products across the menu) so no schema or
 * API change is needed. Swap the implementation here if real data lands later.
 */
import type { CategoryPublic, ProductPublic } from '@/lib/schemas/menu'

/** First `n` products across all categories, preserving menu order. */
export function pickPopular(categories: CategoryPublic[], n: number): ProductPublic[] {
  const out: ProductPublic[] = []
  for (const cat of categories) {
    for (const p of cat.products) {
      out.push(p)
      if (out.length >= n) return out
    }
  }
  return out
}

/** The first product on the menu, used as the static "Chef's Special". */
export function pickFeatured(categories: CategoryPublic[]): ProductPublic | undefined {
  for (const cat of categories) {
    if (cat.products.length > 0) return cat.products[0]
  }
  return undefined
}

/** True when a product id is in the precomputed "popular" set (gets a badge). */
export function makeBestsellerSet(popular: ProductPublic[]): Set<string> {
  return new Set(popular.map((p) => p.id))
}
