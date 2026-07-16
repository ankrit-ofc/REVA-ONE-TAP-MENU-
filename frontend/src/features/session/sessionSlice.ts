import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

interface SessionState {
  sessionToken: string | null
  tableName: string | null
  restaurantName: string | null
  expiresAt: string | null
}

const initialState: SessionState = {
  sessionToken: null,
  tableName: null,
  restaurantName: null,
  expiresAt: null,
}

const sessionSlice = createSlice({
  name: 'session',
  initialState,
  reducers: {
    setSession(
      state,
      action: PayloadAction<{
        sessionToken: string
        tableName: string
        restaurantName: string
        expiresAt: string
      }>,
    ) {
      state.sessionToken = action.payload.sessionToken
      state.tableName = action.payload.tableName
      state.restaurantName = action.payload.restaurantName
      state.expiresAt = action.payload.expiresAt
    },
    clearSession(state) {
      state.sessionToken = null
      state.tableName = null
      state.restaurantName = null
      state.expiresAt = null
    },
  },
})

export const { setSession, clearSession } = sessionSlice.actions
export default sessionSlice.reducer
