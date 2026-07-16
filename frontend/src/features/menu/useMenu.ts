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
    return findInTree(data ?? [], productId)
  }

  return { categories: data ?? [], isLoading, isError, refetch, findProduct }
}
