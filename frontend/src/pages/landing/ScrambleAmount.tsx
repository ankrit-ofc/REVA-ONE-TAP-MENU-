import { useEffect, useRef } from 'react'

interface Props {
  monthly: string
  yearly: string
  /** Which price is currently shown. Changing this triggers the scramble. */
  isYearly: boolean
}

const DIGITS = '0123456789'

/**
 * Pricing amount with a HyperText-style digit scramble when the billing period
 * flips. Commas/spaces are preserved; digits scramble then settle to the target.
 * The text is managed imperatively via a ref (not React-controlled) so the
 * animation isn't clobbered by re-renders. Under prefers-reduced-motion it snaps.
 */
export default function ScrambleAmount({ monthly, yearly, isYearly }: Props) {
  const ref = useRef<HTMLSpanElement>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const first = useRef(true)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const target = isYearly ? yearly : monthly

    const reduce =
      typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
    // No animation on first paint or under reduced motion — just show the value.
    if (first.current || reduce) {
      first.current = false
      el.textContent = target
      return
    }

    const chars = target.split('')
    if (timer.current) clearInterval(timer.current)
    let iter = 0
    const tick = () => {
      el.textContent = chars
        .map((c, i) => (/[^0-9]/.test(c) ? c : i <= iter ? c : DIGITS[Math.floor(Math.random() * 10)]))
        .join('')
      if (iter >= chars.length) {
        if (timer.current) clearInterval(timer.current)
        el.textContent = target
        return
      }
      iter += 0.18
    }
    timer.current = setInterval(tick, Math.max(30, 1600 / (chars.length * 14)))
    tick()

    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [isYearly, monthly, yearly])

  return <span className="amount" ref={ref}>{monthly}</span>
}
