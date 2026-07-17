import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { formatPrice } from '@/lib/currency'
import { prefetchModel } from '@/features/ar/modelPrefetch'
import type { ProductPublic } from '@/lib/schemas/menu'
import styles from './SpecialsCarousel.module.css'

interface Props {
  specials: ProductPublic[]
  currency: string
}

/** Same price label rule as ProductCard: cheapest variant with "from", else base. */
function priceLabel(product: ProductPublic, currency: string): string {
  const minVariant = product.variants.length > 0
    ? Math.min(...product.variants.map((v) => v.price))
    : product.base_price
  return product.has_variants
    ? `from ${formatPrice(minVariant, currency)}`
    : formatPrice(product.base_price, currency)
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return reduced
}

const SWIPE_THRESHOLD_PX = 40
const AUTO_ADVANCE_MS = 5000

/**
 * Center-focused carousel for Today's Special. The active slide is large and
 * opaque; neighbours peek from the sides, smaller and dimmed. Tapping the
 * centered slide opens the product detail page — the exact behaviour of
 * ProductCard — while tapping a peeking slide just brings it to the center.
 */
export default function SpecialsCarousel({ specials, currency }: Props) {
  const navigate = useNavigate()
  const count = specials.length
  const reducedMotion = usePrefersReducedMotion()

  const [index, setIndex] = useState(0)
  const [dragX, setDragX] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const touchStartX = useRef<number | null>(null)
  // Mirrors dragX for the touchend decision: a fast flick can end before React
  // re-renders, which would leave the dragX closure value stale.
  const dragXRef = useRef(0)
  // click fires after touchend on mobile; swallow the one that follows a swipe.
  const suppressClick = useRef(false)

  // A removed special can leave the index past the end; snap back in range.
  useEffect(() => {
    if (index >= count) setIndex(0)
  }, [index, count])

  const next = () => setIndex((i) => (i + 1) % count)
  const prev = () => setIndex((i) => (i - 1 + count) % count)

  // Auto-advance, paused while the user is touching, hovering, or focused
  // inside the carousel, and disabled entirely for reduced motion or <2 items.
  const paused = dragging || hovered || focused
  useEffect(() => {
    if (count < 2 || paused || reducedMotion) return
    const id = window.setInterval(() => setIndex((i) => (i + 1) % count), AUTO_ADVANCE_MS)
    return () => window.clearInterval(id)
  }, [count, paused, reducedMotion])

  const onTouchStart = (e: React.TouchEvent) => {
    // New gesture: clear a leftover suppress flag from a swipe whose click the
    // browser never fired (moved touches usually don't produce one).
    suppressClick.current = false
    touchStartX.current = e.touches[0].clientX
    setDragging(true)
  }
  const onTouchMove = (e: React.TouchEvent) => {
    if (touchStartX.current == null) return
    const delta = e.touches[0].clientX - touchStartX.current
    dragXRef.current = delta
    setDragX(delta)
  }
  const onTouchEnd = () => {
    const delta = dragXRef.current
    if (Math.abs(delta) > 10) suppressClick.current = true
    if (count > 1) {
      if (delta <= -SWIPE_THRESHOLD_PX) next()
      else if (delta >= SWIPE_THRESHOLD_PX) prev()
    }
    touchStartX.current = null
    dragXRef.current = 0
    setDragX(0)
    setDragging(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (count < 2) return
    if (e.key === 'ArrowRight') { e.preventDefault(); next() }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); prev() }
  }

  const openProduct = (p: ProductPublic) => navigate(`/product/${p.id}`)

  return (
    <div
      className={styles.carousel}
      role="group"
      aria-roledescription="carousel"
      aria-label="Today's special dishes"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    >
      <div
        className={styles.viewport}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
      >
        {specials.map((p, i) => {
          // Signed shortest distance from the active slide, so with 2 items the
          // other one appears on one side only (never duplicated on both).
          let d = (i - index + count) % count
          if (d > count / 2) d -= count
          const isActive = d === 0
          const offstage = Math.abs(d) > 1

          const drag = dragging ? dragX : 0
          const transform =
            `translateX(calc(-50% + ${d * 72}% + ${drag}px)) ` +
            `scale(${isActive ? 1 : 0.78})`

          return (
            <div
              key={p.id}
              className={
                `${styles.item} ${isActive ? styles.itemActive : ''} ` +
                `${offstage ? styles.itemOffstage : ''} ${dragging ? styles.noTransition : ''}`
              }
              style={{ transform, zIndex: isActive ? 2 : 1 }}
              aria-hidden={!isActive}
              onClick={() => {
                if (suppressClick.current) { suppressClick.current = false; return }
                if (isActive) openProduct(p)
                else setIndex(i)
              }}
              onPointerDown={() => {
                if (isActive && p.model_glb_url) prefetchModel(p.model_glb_url)
              }}
              role={isActive ? 'button' : undefined}
              aria-label={isActive ? `${p.name}, ${priceLabel(p, currency)}` : undefined}
            >
              {p.image_url
                ? <img className={styles.image} src={p.image_url} alt={p.name} loading="lazy" draggable={false} />
                : <div className={styles.imagePlaceholder} aria-hidden>🍽️</div>}
              <div className={styles.caption}>
                <span className={styles.name}>{p.name}</span>
                <span className={styles.price}>{priceLabel(p, currency)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {count > 1 && (
        <div className={styles.controls}>
          <button
            type="button"
            className={styles.arrow}
            onClick={prev}
            aria-label="Previous special"
          >
            ‹
          </button>
          <button
            type="button"
            className={styles.arrow}
            onClick={next}
            aria-label="Next special"
          >
            ›
          </button>
        </div>
      )}
    </div>
  )
}
