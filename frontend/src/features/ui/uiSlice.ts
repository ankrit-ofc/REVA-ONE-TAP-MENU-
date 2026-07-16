import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'reva-theme'

function readInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* localStorage unavailable (SSR / privacy mode) — fall back to light */
  }
  return 'light'
}

interface UiState {
  theme: Theme
}

const initialState: UiState = {
  theme: readInitialTheme(),
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setTheme(state, action: PayloadAction<Theme>) {
      state.theme = action.payload
    },
    toggleTheme(state) {
      state.theme = state.theme === 'light' ? 'dark' : 'light'
    },
  },
})

export const { setTheme, toggleTheme } = uiSlice.actions
export default uiSlice.reducer
export { STORAGE_KEY as THEME_STORAGE_KEY }
