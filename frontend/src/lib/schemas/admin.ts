import { z } from 'zod'
import { menuTemplateSchema, HEX_COLOR_PATTERN } from './menu'

export const categoryResponseSchema = z.object({
  id: z.string().uuid(),
  restaurant_id: z.string().uuid(),
  parent_id: z.string().uuid().nullable(),
  name: z.string(),
  display_order: z.number().int(),
  is_active: z.boolean(),
  is_available: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const addonResponseSchema = z.object({
  id: z.string().uuid(),
  restaurant_id: z.string().uuid(),
  name: z.string(),
  price: z.coerce.number(),
  is_active: z.boolean(),
})

export const addonMappingResponseSchema = z.object({
  id: z.string().uuid(),
  product_id: z.string().uuid(),
  addon_id: z.string().uuid(),
  addon: addonResponseSchema,
})

export const variantResponseSchema = z.object({
  id: z.string().uuid(),
  product_id: z.string().uuid(),
  restaurant_id: z.string().uuid(),
  name: z.string(),
  price: z.coerce.number(),
  is_active: z.boolean(),
})

export const foodTypeSchema = z.enum(['VEG', 'NON_VEG', 'EGG', 'BEVERAGE', 'SMOKE'])
export type FoodType = z.infer<typeof foodTypeSchema>

export const productResponseSchema = z.object({
  id: z.string().uuid(),
  restaurant_id: z.string().uuid(),
  category_id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable(),
  base_price: z.coerce.number(),
  tax_rate: z.coerce.number(),
  food_type: foodTypeSchema,
  is_available: z.boolean(),
  is_active: z.boolean(),
  has_variants: z.boolean(),
  allows_addons: z.boolean(),
  is_todays_special: z.boolean(),
  image_url: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

// ── AR / 3D model (optional, per-product) ──────────────────────────────────

export const productViewSchema = z.enum(['FRONT', 'BACK', 'LEFT', 'RIGHT', 'TOP'])
export type ProductView = z.infer<typeof productViewSchema>

export const arModelStatusSchema = z.enum([
  'NONE',
  'PENDING',
  'GENERATING',
  'READY',
  'FAILED',
])
export type ArModelStatus = z.infer<typeof arModelStatusSchema>

export const productViewImageResponseSchema = z.object({
  id: z.string().uuid(),
  product_id: z.string().uuid(),
  view: productViewSchema,
  image_url: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const generationJobResponseSchema = z.object({
  id: z.string().uuid(),
  product_id: z.string().uuid(),
  kind: z.enum(['GENERATION', 'MARKING']),
  provider: z.string(),
  status: z.enum(['QUEUED', 'RUNNING', 'DONE', 'FAILED']),
  external_job_id: z.string().nullable(),
  error: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const annotationResponseSchema = z.object({
  id: z.string().uuid(),
  product_id: z.string().uuid(),
  label: z.string(),
  position_x: z.number(),
  position_y: z.number(),
  position_z: z.number(),
  normal_x: z.number(),
  normal_y: z.number(),
  normal_z: z.number(),
  calories: z.coerce.number().nullable(),
  protein_g: z.coerce.number().nullable(),
  carbs_g: z.coerce.number().nullable(),
  fat_g: z.coerce.number().nullable(),
  allergens: z.array(z.string()),
  source: z.enum(['AI', 'MANUAL']),
  status: z.enum(['AI_ESTIMATED', 'ADMIN_VERIFIED']),
  created_at: z.string(),
  updated_at: z.string(),
})

export const modelStatusResponseSchema = z.object({
  product_id: z.string().uuid(),
  model_status: arModelStatusSchema,
  model_glb_url: z.string().nullable(),
  model_usdz_url: z.string().nullable(),
  model_published: z.boolean(),
  views: z.array(productViewImageResponseSchema),
  jobs: z.array(generationJobResponseSchema),
  annotations: z.array(annotationResponseSchema),
})

export type ProductViewImageResponse = z.infer<typeof productViewImageResponseSchema>
export type GenerationJobResponse = z.infer<typeof generationJobResponseSchema>
export type AnnotationResponse = z.infer<typeof annotationResponseSchema>
export type ModelStatusResponse = z.infer<typeof modelStatusResponseSchema>

export const settingsResponseSchema = z.object({
  id: z.string().uuid(),
  restaurant_id: z.string().uuid(),
  waiter_can_accept_payment: z.boolean(),
  allow_order_reopen: z.boolean(),
  require_order_approval: z.boolean(),
  currency: z.string(),
  timezone: z.string(),
  require_location: z.boolean(),
  latitude: z.number().nullable(),
  longitude: z.number().nullable(),
  geofence_radius_meters: z.number(),
  print_kot_enabled: z.boolean(),
  print_bill_enabled: z.boolean(),
  bill_copies: z.number(),
  kot_print_mode: z.enum(['browser', 'worker']),
  kot_printer_name: z.string().nullable(),
  kot_worker_token: z.string().nullable(),
  // Customer-menu hero image; set only via the banner upload endpoint.
  banner_image_url: z.string().nullable(),
  // Payment QR shown at billing; set only via the payment-qr upload endpoint.
  payment_qr_url: z.string().nullable(),
  // Customer-menu presentation (admin Settings → "Edit menu").
  menu_template: menuTemplateSchema,
  menu_accent_color: z.string().nullable(),
  specials_section_title: z.string().nullable(),
  // Read-only STORED restaurants flags (not editable on Settings).
  ar_enabled: z.boolean().optional(),
  qr_pay_enabled: z.boolean().optional(),
})

export const categoryCreateSchema = z.object({
  name: z.string().min(1).max(80),
  display_order: z.number().int().min(0),
  is_available: z.boolean().default(true),
  parent_id: z.string().uuid().nullable().optional(),
})

export const productCreateSchema = z.object({
  category_id: z.string().uuid(),
  name: z.string().min(1).max(120),
  description: z.string().max(255).nullable().optional(),
  base_price: z.number().min(0),
  tax_rate: z.number().min(0).max(100),
  food_type: foodTypeSchema,
  is_available: z.boolean(),
  has_variants: z.boolean(),
  allows_addons: z.boolean(),
})

// ── Product CSV Import ──────────────────────────────────────────────────────

export const importRowErrorSchema = z.object({
  row: z.number(),
  field: z.string(),
  message: z.string(),
  raw: z.string(),
})

export const importPreviewResponseSchema = z.object({
  valid_rows: z.number(),
  products_to_create: z.number(),
  duplicates_skipped: z.number(),
  new_categories: z.array(z.string()),
  existing_categories: z.array(z.string()),
  errors: z.array(importRowErrorSchema),
})

export const importCommitResponseSchema = z.object({
  categories_created: z.number(),
  products_created: z.number(),
  duplicates_skipped: z.number(),
})

export type ImportRowError = z.infer<typeof importRowErrorSchema>
export type ImportPreviewResponse = z.infer<typeof importPreviewResponseSchema>
export type ImportCommitResponse = z.infer<typeof importCommitResponseSchema>

export const settingsUpdateSchema = z.object({
  enable_qr_payment: z.boolean().optional(), // soft-deprecated; ignored by backend
  waiter_can_accept_payment: z.boolean().optional(),
  allow_order_reopen: z.boolean().optional(),
  require_order_approval: z.boolean().optional(),
  currency: z.string().min(3).max(3).optional(),
  timezone: z.string().min(1).max(100).optional(),
  require_location: z.boolean().optional(),
  latitude: z.number().optional(),
  longitude: z.number().optional(),
  geofence_radius_meters: z.number().optional(),
  print_kot_enabled: z.boolean().optional(),
  print_bill_enabled: z.boolean().optional(),
  bill_copies: z.number().optional(),
  kot_print_mode: z.enum(['browser', 'worker']).optional(),
  kot_printer_name: z.string().max(120).optional(),
  menu_template: menuTemplateSchema.optional(),
  menu_accent_color: z.string().regex(HEX_COLOR_PATTERN).optional(),
  specials_section_title: z.string().max(80).optional(),
})

// Counter-readable subset of the printer settings.
export const printConfigSchema = z.object({
  print_kot_enabled: z.boolean(),
  print_bill_enabled: z.boolean(),
  bill_copies: z.number(),
  kot_print_mode: z.enum(['browser', 'worker']),
  kot_printer_name: z.string().nullable(),
})
export type PrintConfig = z.infer<typeof printConfigSchema>

export const staffResponseSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  role: z.enum(['SUPERADMIN', 'ADMIN', 'KITCHEN', 'WAITER', 'COUNTER', 'COUNTER_DISPLAY']),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const tableResponseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  qr_token: z.string().optional(),
  scan_url: z.string().optional(),
})

// ── Dashboard widgets ──────────────────────────────────────────────────────
export const activeTableItemSchema = z.object({
  name: z.string(),
  quantity: z.number(),
})
export const activeTableOrderSchema = z.object({
  order_id: z.string().uuid(),
  order_number: z.number(),
  status: z.enum(['OPEN', 'MEAL_FINISHED', 'CLOSED']),
  placed_at: z.string(),
  items: z.array(activeTableItemSchema),
})
export const activeTableSchema = z.object({
  table_id: z.string().uuid(),
  table_label: z.string(),
  order_count: z.number(),
  earliest_placed_at: z.string(),
  total_amount: z.coerce.number(),
  orders: z.array(activeTableOrderSchema),
})
export const revenueTodaySchema = z.object({
  amount: z.coerce.number().nullable(),
  currency: z.string(),
})
export const ordersThisWeekSchema = z.object({
  count: z.number(),
})
export const topProductSchema = z.object({
  product_name: z.string(),
  quantity_sold: z.number(),
})
export const topProductsSchema = z.object({
  window_days: z.number(),
  products: z.array(topProductSchema),
})

export type ActiveTable = z.infer<typeof activeTableSchema>
export type ActiveTableOrder = z.infer<typeof activeTableOrderSchema>
export type RevenueToday = z.infer<typeof revenueTodaySchema>
export type OrdersThisWeek = z.infer<typeof ordersThisWeekSchema>
export type TopProducts = z.infer<typeof topProductsSchema>

export type CategoryResponse = z.infer<typeof categoryResponseSchema>
export type ProductResponse = z.infer<typeof productResponseSchema>
export type VariantResponse = z.infer<typeof variantResponseSchema>
export type AddonResponse = z.infer<typeof addonResponseSchema>
export type AddonMappingResponse = z.infer<typeof addonMappingResponseSchema>
export type SettingsResponse = z.infer<typeof settingsResponseSchema>
export type CategoryCreate = z.infer<typeof categoryCreateSchema>
export type ProductCreate = z.infer<typeof productCreateSchema>
export type SettingsUpdate = z.infer<typeof settingsUpdateSchema>
export type StaffResponse = z.infer<typeof staffResponseSchema>
export type TableResponse = z.infer<typeof tableResponseSchema>
