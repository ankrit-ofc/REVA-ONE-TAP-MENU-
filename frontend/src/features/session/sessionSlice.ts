import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

interface SessionState {
  sessionToken: string | null
  tableName: string | null
  restaurantName: string | null
  expiresAt: string | null
  /** COMPUTED flags from scan/menu. null = unknown (treat as enabled). */
  orderEnabled: boolean | null
  callWaiterEnabled: boolean | null
  arEnabled: boolean | null
  qrPaymentEnabled: boolean | null
  /** Menu theming, set from GET /menu (setFeatureFlags only — /scan doesn't
   *  carry it). null = not fetched yet; consumers fall back to defaults. */
  menuTemplate: string | null
  menuAccentColor: string | null
}

const initialState: SessionState = {
  sessionToken: null,
  tableName: null,
  restaurantName: null,
  expiresAt: null,
  orderEnabled: null,
  callWaiterEnabled: null,
  arEnabled: null,
  qrPaymentEnabled: null,
  menuTemplate: null,
  menuAccentColor: null,
}

function flagOrNull(v: boolean | undefined): boolean | null {
  return v === undefined ? null : v
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
        orderEnabled?: boolean
        callWaiterEnabled?: boolean
        arEnabled?: boolean
        qrPaymentEnabled?: boolean
      }>,
    ) {
      state.sessionToken = action.payload.sessionToken
      state.tableName = action.payload.tableName
      state.restaurantName = action.payload.restaurantName
      state.expiresAt = action.payload.expiresAt
      state.orderEnabled = flagOrNull(action.payload.orderEnabled)
      state.callWaiterEnabled = flagOrNull(action.payload.callWaiterEnabled)
      state.arEnabled = flagOrNull(action.payload.arEnabled)
      state.qrPaymentEnabled = flagOrNull(action.payload.qrPaymentEnabled)
    },
    setFeatureFlags(
      state,
      action: PayloadAction<{
        orderEnabled?: boolean
        callWaiterEnabled?: boolean
        arEnabled?: boolean
        qrPaymentEnabled?: boolean
        menuTemplate?: string
        menuAccentColor?: string | null
      }>,
    ) {
      if (action.payload.orderEnabled !== undefined) {
        state.orderEnabled = action.payload.orderEnabled
      }
      if (action.payload.callWaiterEnabled !== undefined) {
        state.callWaiterEnabled = action.payload.callWaiterEnabled
      }
      if (action.payload.arEnabled !== undefined) {
        state.arEnabled = action.payload.arEnabled
      }
      if (action.payload.qrPaymentEnabled !== undefined) {
        state.qrPaymentEnabled = action.payload.qrPaymentEnabled
      }
      if (action.payload.menuTemplate !== undefined) {
        state.menuTemplate = action.payload.menuTemplate
      }
      if (action.payload.menuAccentColor !== undefined) {
        state.menuAccentColor = action.payload.menuAccentColor
      }
    },
    clearSession(state) {
      state.sessionToken = null
      state.tableName = null
      state.restaurantName = null
      state.expiresAt = null
      state.orderEnabled = null
      state.callWaiterEnabled = null
      state.arEnabled = null
      state.qrPaymentEnabled = null
      state.menuTemplate = null
      state.menuAccentColor = null
    },
  },
})

export const { setSession, setFeatureFlags, clearSession } = sessionSlice.actions
export default sessionSlice.reducer
