import { useState } from 'react'
import type { ComponentType, SVGProps } from 'react'

export interface ExpandPanel {
  icon: ComponentType<SVGProps<SVGSVGElement>>
  title: string
  body: string
  /** Optional background image (Features variant). */
  image?: string
}

interface Props {
  panels: ExpandPanel[]
  /** Renders the translucent-on-green variant used inside the Benefits band. */
  onGreen?: boolean
}

/**
 * Row of panels where the hovered/focused/tapped panel expands and reveals its
 * copy; the rest collapse to a vertical label. On narrow screens the CSS stacks
 * them and shows every panel's copy (see landing.css). Keyboard reachable via
 * tabIndex + focus.
 */
export default function ExpandRow({ panels, onGreen = false }: Props) {
  const [active, setActive] = useState(0)

  return (
    <div className={onGreen ? 'expand-row on-green reveal' : 'expand-row reveal'}>
      {panels.map((p, i) => {
        const Icon = p.icon
        const hasImg = Boolean(p.image)
        const cls = ['ep', hasImg ? 'has-img' : '', i === active ? 'active' : ''].filter(Boolean).join(' ')
        return (
          <article
            key={p.title}
            className={cls}
            tabIndex={0}
            style={hasImg ? { backgroundImage: `url('${p.image}')` } : undefined}
            onMouseEnter={() => setActive(i)}
            onFocus={() => setActive(i)}
            onClick={() => setActive(i)}
          >
            <span className="ep-icon"><Icon /></span>
            <div className="ep-body">
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </div>
            <span className="ep-label"><b>{p.title}</b></span>
          </article>
        )
      })}
    </div>
  )
}
