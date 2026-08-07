import { useGetMenuQuery } from './menuApi'
import type { CategoryPublic, ProductPublic } from '@/lib/schemas/menu'

/** Depth-first search for a product across the whole category tree. */
function findInTree(cats: CategoryPublic[], productId: string): ProductPublic | undefined {
  for (const cat of cats) {
    const p = cat.products.find((p) => p.id === productId)
    if (p) return p
    const nested = findInTree(cat.children, productId)
    if (nested) return nested
  }
  return undefined
}

export function useMenu() {
  const { data, isLoading, isError, refetch } = useGetMenuQuery()

  function findProduct(productId: string): ProductPublic | undefined {
    return (
      data?.specials.find((p) => p.id === productId) ??
      findInTree(data?.categories ?? [], productId)
    )
  }

  return {
    categories: data?.categories ?? [],
    specials: data?.specials ?? [],
    bannerImageUrl: data?.banner_image_url ?? null,
    specialsSectionTitle: data?.specials_section_title ?? null,
    popupEnabled: data?.popup_enabled ?? false,
    popupBadgeText: data?.popup_badge_text ?? null,
    popupHeadline: data?.popup_headline ?? null,
    popupMastheadSubline: data?.popup_masthead_subline ?? null,
    popupBubbleText: data?.popup_bubble_text ?? null,
    popupKicker: data?.popup_kicker ?? null,
    popupTagline: data?.popup_tagline ?? null,
    popupSectionLabel: data?.popup_section_label ?? null,
    popupCtaText: data?.popup_cta_text ?? null,
    popupFooterText: data?.popup_footer_text ?? null,
    popupIllustrationUrl: data?.popup_illustration_url ?? null,
    popupProductIds: data?.popup_product_ids ?? [],
    isLoading,
    isError,
    refetch,
    findProduct,
  }
}
