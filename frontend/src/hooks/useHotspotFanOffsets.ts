import { useEffect, useRef, useState, type RefObject } from 'react'

export interface FanOffset {
  /** px, relative to the hotspot's own anchor point (the dot). */
  lx: number
  ly: number
  /** px — leader-line length, same magnitude as the lx/ly vector. */
  len: number
  /** deg — leader-line rotation, pointing from the dot toward the card. */
  ang: number
}

interface Options {
  /** Leader length as a fraction of the viewer container's shorter side. */
  radiusFactor?: number
  minRadius?: number
  maxRadius?: number
  /** Pause the per-frame loop, e.g. while the viewer is hidden/unmounted. */
  active?: boolean
}

const EPSILON_PX = 0.5

/**
 * Continuously computes, per hotspot id, a pixel offset — relative to that
 * hotspot's own anchor point — that points its card radially OUTWARD from the
 * <model-viewer> container's center, so the card clears the dish's screen-space
 * footprint at any camera angle.
 *
 * Recomputed every animation frame rather than on model-viewer's `camera-change`
 * event: auto-rotate advances the camera by writing `scene.yaw` directly on each
 * internal tick (see StagingModelViewerElement[$tick] in
 * @google/model-viewer/lib/features/staging.js) and never dispatches
 * `camera-change` — an event-driven approach would freeze the fan direction the
 * moment auto-rotate takes over. Re-renders are skipped when nothing moved more
 * than EPSILON_PX, so an idle camera (the common admin-editor case) costs one
 * rAF callback with no state update, not one render per frame.
 */
export function useHotspotFanOffsets(
  viewerRef: RefObject<HTMLElement | null>,
  dotRefs: RefObject<Map<string, HTMLElement>>,
  ids: string[],
  { radiusFactor = 0.42, minRadius = 70, maxRadius = 220, active = true }: Options = {},
): Record<string, FanOffset> {
  const [offsets, setOffsets] = useState<Record<string, FanOffset>>({})
  const lastRef = useRef<Record<string, FanOffset>>({})
  const idsKey = ids.join(',')

  useEffect(() => {
    if (!active || ids.length === 0) return
    const viewer = viewerRef.current
    if (!viewer) return

    let raf = 0
    const tick = () => {
      const containerRect = viewer.getBoundingClientRect()
      const cx = containerRect.left + containerRect.width / 2
      const cy = containerRect.top + containerRect.height / 2
      const radius = Math.min(
        maxRadius,
        Math.max(minRadius, Math.min(containerRect.width, containerRect.height) * radiusFactor),
      )

      const next: Record<string, FanOffset> = {}
      ids.forEach((id, i) => {
        const dot = dotRefs.current?.get(id)
        let dx = 0
        let dy = 0
        if (dot) {
          const r = dot.getBoundingClientRect()
          dx = r.left + r.width / 2 - cx
          dy = r.top + r.height / 2 - cy
        }
        // Anchor projects ~exactly to the container center (rare) or hasn't been
        // positioned by model-viewer yet — fall back to an index-based direction
        // so the card still has a defined fan-out angle instead of collapsing to 0,0.
        if (Math.hypot(dx, dy) < 1) {
          const fallback = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, ids.length)
          dx = Math.cos(fallback)
          dy = Math.sin(fallback)
        }
        const mag = Math.hypot(dx, dy)
        const ux = dx / mag
        const uy = dy / mag
        next[id] = { lx: ux * radius, ly: uy * radius, len: radius, ang: (Math.atan2(uy, ux) * 180) / Math.PI }
      })

      const changed = ids.some((id) => {
        const prev = lastRef.current[id]
        const cur = next[id]
        return !prev || Math.abs(prev.lx - cur.lx) > EPSILON_PX || Math.abs(prev.ly - cur.ly) > EPSILON_PX
      })
      if (changed) {
        lastRef.current = next
        setOffsets(next)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // dotRefs is a stable ref container; radius bounds are read fresh each tick via closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewerRef, dotRefs, idsKey, active, radiusFactor, minRadius, maxRadius])

  return offsets
}
