import { useEffect, useRef, useState } from 'react'

interface Props {
  /** Final value to count up to. */
  to: number
  /** Rendered before the number (e.g. "Rs. "). */
  prefix?: string
  /** Rendered after the number (e.g. "+", "%", "K+"). */
  suffix?: string
  durationMs?: number
}

/**
 * Counts up from 0 to `to` the first time it scrolls into view (cubic ease-out),
 * formatted with en-IN grouping. Under prefers-reduced-motion it renders the
 * final value immediately.
 */
export default function Counter({ to, prefix = '', suffix = '', durationMs = 1600 }: Props) {
  const ref = useRef<HTMLSpanElement>(null)
  const [value, setValue] = useState(0)
  const done = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const reduce =
      typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce || typeof IntersectionObserver === 'undefined') {
      setValue(to)
      return
    }

    const run = () => {
      if (done.current) return
      done.current = true
      const start = performance.now()
      const tick = (now: number) => {
        const p = Math.min((now - start) / durationMs, 1)
        const eased = 1 - Math.pow(1 - p, 3)
        setValue(Math.round(to * eased))
        if (p < 1) requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          run()
          io.disconnect()
        }
      },
      { threshold: 0.4 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [to, durationMs])

  return (
    <span ref={ref}>
      {prefix}
      {value.toLocaleString('en-IN')}
      {suffix}
    </span>
  )
}
