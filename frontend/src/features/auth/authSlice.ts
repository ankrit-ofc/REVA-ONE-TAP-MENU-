import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { Role } from '@/types'

interface AuthState {
  isAuthenticated: boolean
  userId: string | null
  restaurantId: string | null
  role: Role | null
  // True when the session ended involuntarily (refresh failed) — e.g. this
  // account signed in on another device (single-session) or the session expired.
  // Drives the notice on the login screen. Manual logout never sets this.
  signedOutNotice: boolean
}

const initialState: AuthState = {
  isAuthenticated: false,
  userId: null,
  restaurantId: null,
  role: null,
  signedOutNotice: false,
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setCredentials(
      state,
      action: PayloadAction<{ userId: string; restaurantId: string; role: Role }>,
    ) {
      state.isAuthenticated = true
      state.userId = action.payload.userId
      state.restaurantId = action.payload.restaurantId
      state.role = action.payload.role
      state.signedOutNotice = false
    },
    // Explicit, user-initiated logout — clears state with no "signed out" notice.
    clearAuth(state) {
      state.isAuthenticated = false
      state.userId = null
      state.restaurantId = null
      state.role = null
      state.signedOutNotice = false
    },
    // Involuntary end-of-session (a refresh attempt failed). Same teardown as
    // clearAuth but raises the login-screen notice.
    sessionEnded(state) {
      state.isAuthenticated = false
      state.userId = null
      state.restaurantId = null
      state.role = null
      state.signedOutNotice = true
    },
  },
})

export const { setCredentials, clearAuth, sessionEnded } = authSlice.actions
export default authSlice.reducer
