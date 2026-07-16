import { z } from 'zod'
import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import {
  productResponseSchema,
  variantResponseSchema,
  addonResponseSchema,
  addonMappingResponseSchema,
  modelStatusResponseSchema,
  productViewImageResponseSchema,
  annotationResponseSchema,
  type CategoryResponse,
  type ProductResponse,
  type VariantResponse,
  type AddonResponse,
  type AddonMappingResponse,
  type SettingsResponse,
  type CategoryCreate,
  type ProductCreate,
  type SettingsUpdate,
  type StaffResponse,
  type TableResponse,
  type FoodType,
  type ModelStatusResponse,
  type ProductViewImageResponse,
  type AnnotationResponse,
  type ProductView,
} from '@/lib/schemas/admin'

/** Nutrition-tag fields the admin can set (create requires a label). */
export interface AnnotationInput {
  label?: string
  calories?: number | null
  protein_g?: number | null
  carbs_g?: number | null
  fat_g?: number | null
  allergens?: string[]
  position_x?: number
  position_y?: number
  position_z?: number
  normal_x?: number
  normal_y?: number
  normal_z?: number
}

interface CategoryUpdate {
  name?: string
  display_order?: number
  is_available?: boolean
  // Re-parent: parent_id_set=true means apply parent_id (null = make root).
  parent_id?: string | null
  parent_id_set?: boolean
}

interface ProductUpdate {
  category_id?: string
  name?: string
  description?: string
  base_price?: number
  tax_rate?: number
  food_type?: FoodType
  is_available?: boolean
  has_variants?: boolean
  allows_addons?: boolean
}

export interface StaffCreate {
  email: string
  password: string
  role: 'ADMIN' | 'KITCHEN' | 'WAITER' | 'COUNTER' | 'COUNTER_DISPLAY'
}

export interface StaffUpdate {
  role?: 'ADMIN' | 'KITCHEN' | 'WAITER' | 'COUNTER' | 'COUNTER_DISPLAY'
  is_active?: boolean
}

export interface TableCreate {
  name: string
}

export interface TableUpdate {
  name?: string
  is_active?: boolean
}

export const adminApi = createApi({
  reducerPath: 'adminApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['Category', 'Product', 'Variant', 'Addon', 'Settings', 'Staff', 'Table', 'ProductModel'],
  endpoints: (builder) => ({
    // ── Categories ─────────────────────────────────────────────────────────
    listCategories: builder.query<CategoryResponse[], void>({
      query: () => ({ method: 'GET', url: '/admin/categories' }),
      providesTags: ['Category'],
    }),
    createCategory: builder.mutation<CategoryResponse, CategoryCreate>({
      query: (body) => ({ method: 'POST', url: '/admin/categories', data: body }),
      invalidatesTags: ['Category'],
    }),
    updateCategory: builder.mutation<CategoryResponse, { id: string } & CategoryUpdate>({
      query: ({ id, ...body }) => ({ method: 'PUT', url: `/admin/categories/${id}`, data: body }),
      invalidatesTags: ['Category'],
    }),
    softDeleteCategory: builder.mutation<CategoryResponse, string>({
      query: (id) => ({ method: 'DELETE', url: `/admin/categories/${id}` }),
      invalidatesTags: ['Category'],
    }),
    // ── Products ───────────────────────────────────────────────────────────
    listProducts: builder.query<ProductResponse[], void>({
      query: () => ({ method: 'GET', url: '/admin/products' }),
      // Coerce Decimal-as-string money fields (base_price, tax_rate).
      transformResponse: parseWith(z.array(productResponseSchema)),
      providesTags: ['Product'],
    }),
    createProduct: builder.mutation<ProductResponse, ProductCreate>({
      query: (body) => ({ method: 'POST', url: '/admin/products', data: body }),
      transformResponse: parseWith(productResponseSchema),
      invalidatesTags: ['Product'],
    }),
    updateProduct: builder.mutation<ProductResponse, { id: string } & ProductUpdate>({
      query: ({ id, ...body }) => ({ method: 'PUT', url: `/admin/products/${id}`, data: body }),
      transformResponse: parseWith(productResponseSchema),
      invalidatesTags: ['Product'],
    }),
    softDeleteProduct: builder.mutation<ProductResponse, string>({
      query: (id) => ({ method: 'DELETE', url: `/admin/products/${id}` }),
      transformResponse: parseWith(productResponseSchema),
      invalidatesTags: ['Product'],
    }),
    uploadProductImage: builder.mutation<ProductResponse, { productId: string; file: File }>({
      query: ({ productId, file }) => {
        const form = new FormData()
        form.append('file', file)
        return { method: 'POST', url: `/admin/products/${productId}/image`, data: form }
      },
      transformResponse: parseWith(productResponseSchema),
      invalidatesTags: ['Product'],
    }),
    // ── AR / 3D model ──────────────────────────────────────────────────────
    getModelStatus: builder.query<ModelStatusResponse, string>({
      query: (productId) => ({ method: 'GET', url: `/admin/products/${productId}/model` }),
      transformResponse: parseWith(modelStatusResponseSchema),
      providesTags: (_r, _e, productId) => [{ type: 'ProductModel', id: productId }],
    }),
    uploadModelView: builder.mutation<
      ProductViewImageResponse,
      { productId: string; view: ProductView; file: File }
    >({
      query: ({ productId, view, file }) => {
        const form = new FormData()
        form.append('file', file)
        return {
          method: 'POST',
          url: `/admin/products/${productId}/model/views/${view}`,
          data: form,
        }
      },
      transformResponse: parseWith(productViewImageResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'ProductModel', id: productId }],
    }),
    generateModel: builder.mutation<ModelStatusResponse, { productId: string; model: string }>({
      query: ({ productId, model }) => ({
        method: 'POST',
        url: `/admin/products/${productId}/model/generate`,
        data: { model },
      }),
      transformResponse: parseWith(modelStatusResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'ProductModel', id: productId }],
    }),
    createAnnotation: builder.mutation<
      AnnotationResponse,
      { productId: string; body: AnnotationInput }
    >({
      query: ({ productId, body }) => ({
        method: 'POST',
        url: `/admin/products/${productId}/annotations`,
        data: body,
      }),
      transformResponse: parseWith(annotationResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'ProductModel', id: productId }],
    }),
    updateAnnotation: builder.mutation<
      AnnotationResponse,
      { productId: string; annotationId: string; body: AnnotationInput }
    >({
      query: ({ productId, annotationId, body }) => ({
        method: 'PUT',
        url: `/admin/products/${productId}/annotations/${annotationId}`,
        data: body,
      }),
      transformResponse: parseWith(annotationResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'ProductModel', id: productId }],
    }),
    deleteAnnotation: builder.mutation<
      AnnotationResponse,
      { productId: string; annotationId: string }
    >({
      query: ({ productId, annotationId }) => ({
        method: 'DELETE',
        url: `/admin/products/${productId}/annotations/${annotationId}`,
      }),
      transformResponse: parseWith(annotationResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'ProductModel', id: productId }],
    }),
    publishModel: builder.mutation<
      ModelStatusResponse,
      { productId: string; published: boolean }
    >({
      query: ({ productId, published }) => ({
        method: 'POST',
        url: `/admin/products/${productId}/model/publish`,
        data: { published },
      }),
      transformResponse: parseWith(modelStatusResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'ProductModel', id: productId }],
    }),
    // ── Variants ───────────────────────────────────────────────────────────
    listVariants: builder.query<VariantResponse[], string>({
      query: (productId) => ({
        method: 'GET',
        url: `/admin/products/${productId}/variants`,
      }),
      transformResponse: parseWith(z.array(variantResponseSchema)),
      providesTags: (_r, _e, productId) => [{ type: 'Variant', id: productId }],
    }),
    createVariant: builder.mutation<VariantResponse, { productId: string; name: string; price: number }>({
      query: ({ productId, ...body }) => ({
        method: 'POST',
        url: `/admin/products/${productId}/variants`,
        data: body,
      }),
      transformResponse: parseWith(variantResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'Variant', id: productId }],
    }),
    updateVariant: builder.mutation<
      VariantResponse,
      { productId: string; variantId: string; name?: string; price?: number }
    >({
      query: ({ productId, variantId, ...body }) => ({
        method: 'PUT',
        url: `/admin/products/${productId}/variants/${variantId}`,
        data: body,
      }),
      transformResponse: parseWith(variantResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'Variant', id: productId }],
    }),
    softDeleteVariant: builder.mutation<VariantResponse, { productId: string; variantId: string }>({
      query: ({ productId, variantId }) => ({
        method: 'DELETE',
        url: `/admin/products/${productId}/variants/${variantId}`,
      }),
      transformResponse: parseWith(variantResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'Variant', id: productId }],
    }),
    // ── Addons ─────────────────────────────────────────────────────────────
    listAddons: builder.query<AddonResponse[], void>({
      query: () => ({ method: 'GET', url: '/admin/addons' }),
      transformResponse: parseWith(z.array(addonResponseSchema)),
      providesTags: ['Addon'],
    }),
    createAddon: builder.mutation<AddonResponse, { name: string; price: number }>({
      query: (body) => ({ method: 'POST', url: '/admin/addons', data: body }),
      transformResponse: parseWith(addonResponseSchema),
      invalidatesTags: ['Addon'],
    }),
    updateAddon: builder.mutation<AddonResponse, { id: string; name?: string; price?: number }>({
      query: ({ id, ...body }) => ({ method: 'PUT', url: `/admin/addons/${id}`, data: body }),
      transformResponse: parseWith(addonResponseSchema),
      invalidatesTags: ['Addon'],
    }),
    softDeleteAddon: builder.mutation<AddonResponse, string>({
      query: (id) => ({ method: 'DELETE', url: `/admin/addons/${id}` }),
      transformResponse: parseWith(addonResponseSchema),
      invalidatesTags: ['Addon'],
    }),
    // ── Addon Mappings ─────────────────────────────────────────────────────
    listProductAddons: builder.query<AddonMappingResponse[], string>({
      query: (productId) => ({
        method: 'GET',
        url: `/admin/products/${productId}/addons`,
      }),
      transformResponse: parseWith(z.array(addonMappingResponseSchema)),
      providesTags: (_r, _e, productId) => [{ type: 'Addon', id: productId }],
    }),
    mapAddon: builder.mutation<AddonMappingResponse, { productId: string; addonId: string }>({
      query: ({ productId, addonId }) => ({
        method: 'POST',
        url: `/admin/products/${productId}/addons`,
        data: { addon_id: addonId },
      }),
      transformResponse: parseWith(addonMappingResponseSchema),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'Addon', id: productId }],
    }),
    unmapAddon: builder.mutation<void, { productId: string; addonId: string }>({
      query: ({ productId, addonId }) => ({
        method: 'DELETE',
        url: `/admin/products/${productId}/addons/${addonId}`,
      }),
      invalidatesTags: (_r, _e, { productId }) => [{ type: 'Addon', id: productId }],
    }),
    // ── Settings ───────────────────────────────────────────────────────────
    getSettings: builder.query<SettingsResponse, void>({
      query: () => ({ method: 'GET', url: '/admin/settings' }),
      providesTags: ['Settings'],
    }),
    updateSettings: builder.mutation<SettingsResponse, SettingsUpdate>({
      query: (body) => ({ method: 'PUT', url: '/admin/settings', data: body }),
      invalidatesTags: ['Settings'],
    }),
    rotateKotWorkerToken: builder.mutation<SettingsResponse, void>({
      query: () => ({ method: 'POST', url: '/admin/settings/kot-worker-token' }),
      invalidatesTags: ['Settings'],
    }),
    // ── Staff ──────────────────────────────────────────────────────────────
    listStaff: builder.query<StaffResponse[], void>({
      query: () => ({ method: 'GET', url: '/admin/staff' }),
      providesTags: ['Staff'],
    }),
    createStaff: builder.mutation<StaffResponse, StaffCreate>({
      query: (body) => ({ method: 'POST', url: '/admin/staff', data: body }),
      invalidatesTags: ['Staff'],
    }),
    updateStaff: builder.mutation<StaffResponse, { id: string } & StaffUpdate>({
      query: ({ id, ...body }) => ({ method: 'PUT', url: `/admin/staff/${id}`, data: body }),
      invalidatesTags: ['Staff'],
    }),
    deleteStaff: builder.mutation<StaffResponse, string>({
      query: (id) => ({ method: 'DELETE', url: `/admin/staff/${id}` }),
      invalidatesTags: ['Staff'],
    }),
    // ── Tables ─────────────────────────────────────────────────────────────
    listTables: builder.query<TableResponse[], void>({
      query: () => ({ method: 'GET', url: '/admin/tables' }),
      providesTags: ['Table'],
    }),
    createTable: builder.mutation<TableResponse, TableCreate>({
      query: (body) => ({ method: 'POST', url: '/admin/tables', data: body }),
      invalidatesTags: ['Table'],
    }),
    updateTable: builder.mutation<TableResponse, { id: string } & TableUpdate>({
      query: ({ id, ...body }) => ({ method: 'PUT', url: `/admin/tables/${id}`, data: body }),
      invalidatesTags: ['Table'],
    }),
    deactivateTable: builder.mutation<TableResponse, string>({
      query: (id) => ({ method: 'DELETE', url: `/admin/tables/${id}` }),
      invalidatesTags: ['Table'],
    }),
  }),
})

export const {
  useListCategoriesQuery,
  useCreateCategoryMutation,
  useUpdateCategoryMutation,
  useSoftDeleteCategoryMutation,
  useListProductsQuery,
  useCreateProductMutation,
  useUpdateProductMutation,
  useSoftDeleteProductMutation,
  useUploadProductImageMutation,
  useGetModelStatusQuery,
  useUploadModelViewMutation,
  useGenerateModelMutation,
  useCreateAnnotationMutation,
  useUpdateAnnotationMutation,
  useDeleteAnnotationMutation,
  usePublishModelMutation,
  useListVariantsQuery,
  useCreateVariantMutation,
  useUpdateVariantMutation,
  useSoftDeleteVariantMutation,
  useListAddonsQuery,
  useCreateAddonMutation,
  useUpdateAddonMutation,
  useSoftDeleteAddonMutation,
  useListProductAddonsQuery,
  useMapAddonMutation,
  useUnmapAddonMutation,
  useGetSettingsQuery,
  useUpdateSettingsMutation,
  useRotateKotWorkerTokenMutation,
  useListStaffQuery,
  useCreateStaffMutation,
  useUpdateStaffMutation,
  useDeleteStaffMutation,
  useListTablesQuery,
  useCreateTableMutation,
  useUpdateTableMutation,
  useDeactivateTableMutation,
} = adminApi
