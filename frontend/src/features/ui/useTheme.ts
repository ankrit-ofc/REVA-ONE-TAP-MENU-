import { useCallback } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import type { RootState, AppDispatch } from '@/store/store'
import { toggleTheme as toggleThemeAction, setTheme as setThemeAction, THEME_STORAGE_KEY, type Theme } from './uiSlice'

/** Customer-surface dark/light theme, persisted to localStorage. */
export function useTheme() {
  const theme = useSelector((s: RootState) => s.ui.theme)
  const dispatch = useDispatch<AppDispatch>()

  const persist = (next: Theme) => {
    try { localStorage.setItem(THEME_STORAGE_KEY, next) } catch { /* ignore */ }
  }

  const toggle = useCallback(() => {
    const next: Theme = theme === 'light' ? 'dark' : 'light'
    persist(next)
    dispatch(toggleThemeAction())
  }, [theme, dispatch])

  const set = useCallback((next: Theme) => {
    persist(next)
    dispatch(setThemeAction(next))
  }, [dispatch])

  return { theme, toggle, set }
}
