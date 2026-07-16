import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import type { RestaurantResponse, RestaurantCreateResponse } from '@/lib/schemas/superadmin'

export interface RestaurantCreate {
  name: string
  slug: string
  admin_email: string
  admin_password: string
}

export interface RestaurantUpdate {
  name?: string
  is_active?: boolean
}

export const superadminApi = createApi({
  reducerPath: 'superadminApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['Restaurant'],
  endpoints: (builder) => ({
    listRestaurants: builder.query<RestaurantResponse[], void>({
      query: () => ({ method: 'GET', url: '/superadmin/restaurants' }),
      providesTags: ['Restaurant'],
    }),
    createRestaurant: builder.mutation<RestaurantCreateResponse, RestaurantCreate>({
      query: (body) => ({ method: 'POST', url: '/superadmin/restaurants', data: body }),
      invalidatesTags: ['Restaurant'],
    }),
    updateRestaurant: builder.mutation<RestaurantResponse, { id: string } & RestaurantUpdate>({
      query: ({ id, ...body }) => ({
        method: 'PUT',
        url: `/superadmin/restaurants/${id}`,
        data: body,
      }),
      invalidatesTags: ['Restaurant'],
    }),
    updateAdminEmail: builder.mutation<
      RestaurantResponse,
      { restaurantId: string; userId: string; email: string }
    >({
      query: ({ restaurantId, userId, email }) => ({
        method: 'PUT',
        url: `/superadmin/restaurants/${restaurantId}/admins/${userId}`,
        data: { email },
      }),
      invalidatesTags: ['Restaurant'],
    }),
  }),
})

export const {
  useListRestaurantsQuery,
  useCreateRestaurantMutation,
  useUpdateRestaurantMutation,
  useUpdateAdminEmailMutation,
} = superadminApi
