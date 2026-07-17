import { useState } from 'react'
import type { ComponentType, SVGProps } from 'react'

export interface FeatCard {
  icon: ComponentType<SVGProps<SVGSVGElement>>
  title: string
  body: string
  image: string
  imageAlt: string
}

interface Props {
  cards: FeatCard[]
  /** Index of the card open on first paint. */
  defaultActive?: number
}

/**
 * Features expand-accordion: the active card grows and reveals its photo +
 * copy; the rest collapse to a number and a footer label. Hover only expands
 * on wide screens (the CSS stacks all cards open below 1020px); focus and tap
 * always work, so it stays keyboard/touch reachable.
 */
export default function FeatAcc({ cards, defaultActive = 0 }: Props) {
  const [active, setActive] = useState(defaultActive)

  return (
    <div className="feat-acc reveal">
      {cards.map((c, i) => {
        const Icon = c.icon
        return (
          <article
            key={c.title}
            className={i === active ? 'fa-card active' : 'fa-card'}
            tabIndex={0}
            onMouseEnter={() => {
              if (matchMedia('(min-width: 1021px)').matches) setActive(i)
            }}
            onFocus={() => setActive(i)}
            onClick={() => setActive(i)}
          >
            <div className="fa-num">{String(i + 1).padStart(2, '0')}.</div>
            <div className="fa-media">
              <img src={c.image} alt={c.imageAlt} loading="lazy" />
            </div>
            <div className="fa-body">
              <span className="fa-icon"><Icon /></span>
              <h3>{c.title}</h3>
              <p>{c.body}</p>
            </div>
            <div className="fa-foot">
              <span className="fa-icon"><Icon /></span>
              <b>{c.title}</b>
            </div>
          </article>
        )
      })}
    </div>
  )
}
