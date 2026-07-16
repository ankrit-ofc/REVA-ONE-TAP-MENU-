/**
 * Helpers to render a FLAT category list (each carrying parent_id) as an indented
 * tree in admin <select> pickers, and to exclude a category's own subtree when
 * choosing its parent (mirrors the backend cycle guard).
 */

export interface CatNode {
  id: string
  name: string
  parent_id: string | null
}

/**
 * Depth-first flatten from roots so children follow their parent, each with a depth
 * for indentation. Sibling order follows the input order (already sorted by the API).
 */
export function indentedCategoryOptions<T extends CatNode>(cats: T[]): { cat: T; depth: number }[] {
  const childrenOf = new Map<string | null, T[]>()
  for (const c of cats) {
    const key = c.parent_id ?? null
    const arr = childrenOf.get(key) ?? []
    arr.push(c)
    childrenOf.set(key, arr)
  }
  const out: { cat: T; depth: number }[] = []
  const walk = (parent: string | null, depth: number) => {
    for (const c of childrenOf.get(parent) ?? []) {
      out.push({ cat: c, depth })
      walk(c.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

/** A category and all its descendants — the set that can't be its own parent. */
export function descendantIdsWithSelf(cats: CatNode[], id: string): Set<string> {
  const childrenOf = new Map<string, string[]>()
  for (const c of cats) {
    if (c.parent_id) {
      const arr = childrenOf.get(c.parent_id) ?? []
      arr.push(c.id)
      childrenOf.set(c.parent_id, arr)
    }
  }
  const result = new Set<string>([id])
  const stack = [id]
  while (stack.length) {
    const cur = stack.pop() as string
    for (const child of childrenOf.get(cur) ?? []) {
      if (!result.has(child)) {
        result.add(child)
        stack.push(child)
      }
    }
  }
  return result
}
