import { z } from 'zod'

// Six customer-menu layouts (admin Settings → "Edit menu"). "classic" is
// today's existing thumbnail-left list and the server_default — theming is
// opt-in, so a restaurant that never picks a template keeps rendering
// classic exactly as it does today. Mirrors backend MENU_TEMPLATES
// (app/schemas/menu.py) — keep in sync.
export const MENU_TEMPLATES = ['classic', 'photo_grid', 'elegant_list', 'compact_list', 'magazine', 'bold_cards'] as const
export const menuTemplateSchema = z.enum(MENU_TEMPLATES)
export type MenuTemplate = z.infer<typeof menuTemplateSchema>
export const HEX_COLOR_PATTERN = /^#[0-9A-Fa-f]{6}$/

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

// Admin-verified per-component nutrition hotspot (customer-facing subset of the admin
// AnnotationResponse — no product_id/source/timestamps). Mirrors backend AnnotationPublic
// (app/schemas/menu.py). Only ever present alongside a published model.
export const annotationPublicSchema = z.object({
  id: z.string().uuid(),
  label: z.string(),
  position_x: z.coerce.number(),
  position_y: z.coerce.number(),
  position_z: z.coerce.number(),
  normal_x: z.coerce.number(),
  normal_y: z.coerce.number(),
  normal_z: z.coerce.number(),
  calories: z.coerce.number().nullable(),
  protein_g: z.coerce.number().nullable(),
  carbs_g: z.coerce.number().nullable(),
  fat_g: z.coerce.number().nullable(),
  allergens: z.array(z.string()),
  status: z.enum(['AI_ESTIMATED', 'ADMIN_VERIFIED']),
})
export type AnnotationPublic = z.infer<typeof annotationPublicSchema>

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
  // Nutrition hotspots for the AR viewer. Optional + nullable so an older cached
  // response (or a backend that hasn't deployed this field yet) never breaks the menu.
  annotations: z.array(annotationPublicSchema).optional().nullable(),
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
// today's specials, and the category tree. Feature flags are COMPUTED
// server-side; optional for backward compat (missing → treat as enabled).
export const menuResponseSchema = z.object({
  banner_image_url: z.string().nullable(),
  specials: z.array(productPublicSchema),
  categories: z.array(categoryPublicSchema),
  order_enabled: z.boolean().optional(),
  call_waiter_enabled: z.boolean().optional(),
  ar_enabled: z.boolean().optional(),
  qr_pay_enabled: z.boolean().optional(),
  // Menu theming. Falls back to classic / no accent when missing (older
  // cached responses, or a backend that hasn't deployed this yet).
  menu_template: menuTemplateSchema.optional(),
  menu_accent_color: z.string().nullable().optional(),
})

export type MenuResponse = z.infer<typeof menuResponseSchema>
