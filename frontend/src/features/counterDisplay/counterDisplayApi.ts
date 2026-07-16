import { z } from 'zod'
import { createApi } from '@reduxjs/toolkit/query/react'
import { axiosBaseQuery } from '@/services/api'
import { parseWith } from '@/lib/parseResponse'
import { displayBoardItemSchema, type DisplayBoardItem } from '@/lib/schemas/board'

export const counterDisplayApi = createApi({
  reducerPath: 'counterDisplayApi',
  baseQuery: axiosBaseQuery,
  tagTypes: ['DisplayBoard'],
  endpoints: (builder) => ({
    getBoard: builder.query<DisplayBoardItem[], void>({
      query: () => ({ method: 'GET', url: '/counter-display/board' }),
      transformResponse: parseWith(z.array(displayBoardItemSchema)),
      providesTags: ['DisplayBoard'],
    }),
  }),
})

export const { useGetBoardQuery } = counterDisplayApi
