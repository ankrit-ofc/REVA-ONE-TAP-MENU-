import type { ComponentType } from 'react'
import type { MenuTemplate, ProductPublic } from '@/lib/schemas/menu'
import ClassicTemplate from './ClassicTemplate'
import PhotoGridTemplate from './PhotoGridTemplate'
import ElegantListTemplate from './ElegantListTemplate'
import CompactListTemplate from './CompactListTemplate'
import MagazineTemplate from './MagazineTemplate'
import BoldCardsTemplate from './BoldCardsTemplate'

export interface MenuTemplateProps {
  products: ProductPublic[]
  currency: string
}

export const MENU_TEMPLATE_COMPONENTS: Record<MenuTemplate, ComponentType<MenuTemplateProps>> = {
  classic: ClassicTemplate,
  photo_grid: PhotoGridTemplate,
  elegant_list: ElegantListTemplate,
  compact_list: CompactListTemplate,
  magazine: MagazineTemplate,
  bold_cards: BoldCardsTemplate,
}

/** Safe lookup for a template id that may not (yet) be a known MenuTemplate —
 *  e.g. stale client code against a newer backend. Falls back to classic —
 *  today's rendering — never to a themed template the restaurant never chose. */
export function resolveMenuTemplate(id: string): ComponentType<MenuTemplateProps> {
  return (MENU_TEMPLATE_COMPONENTS as Record<string, ComponentType<MenuTemplateProps>>)[id]
    ?? MENU_TEMPLATE_COMPONENTS.classic
}
