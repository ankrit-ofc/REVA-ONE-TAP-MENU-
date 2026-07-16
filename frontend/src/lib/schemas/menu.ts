import { z } from 'zod'

export const addonPublicSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  price: z.coerce.number(),
})

export const variantPublicSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  price: z.coerce.number(),
})

export const foodTypePublicSchema = z.enum(['VEG', 'NON_VEG', 'EGG', 'BEVERAGE', 'SMOKE'])
export type FoodTypePublic = z.infer<typeof foodTypePublicSchema>

export const productPublicSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable(),
  base_price: z.coerce.number(),
  tax_rate: z.coerce.number(),
  food_type: foodTypePublicSchema,
  image_url: z.string().nullable(),
  has_variants: z.boolean(),
  allows_addons: z.boolean(),
  variants: z.array(variantPublicSchema),
  addons: z.array(addonPublicSchema),
  // Present only when a model is published — drives the per-dish AR button.
  model_glb_url: z.string().nullable(),
  model_usdz_url: z.string().nullable(),
})

export type AddonPublic = z.infer<typeof addonPublicSchema>
export type VariantPublic = z.infer<typeof variantPublicSchema>
export type ProductPublic = z.infer<typeof productPublicSchema>

// The menu is a tree: each category carries its products AND nested subcategories.
export interface CategoryPublic {
  id: string
  name: string
  display_order: number
  products: ProductPublic[]
  children: CategoryPublic[]
}

// Recursive schema needs z.lazy + an explicit type annotation. Prices inside nested
// products still coerce (via productPublicSchema).
export const categoryPublicSchema: z.ZodType<CategoryPublic> = z.lazy(() =>
  z.object({
    id: z.string().uuid(),
    name: z.string(),
    display_order: z.number().int(),
    products: z.array(productPublicSchema),
    children: z.array(categoryPublicSchema),
  }),
)

// GET /menu payload: per-restaurant hero banner (null → stock image),
// today's specials, and the category tree.
export const menuResponseSchema = z.object({
  banner_image_url: z.string().nullable(),
  specials: z.array(productPublicSchema),
  categories: z.array(categoryPublicSchema),
})

export type MenuResponse = z.infer<typeof menuResponseSchema>
