import { useEffect } from 'react'

/**
 * Calls `handler` whenever the Escape key is pressed, while the component is
 * mounted. Used by modals so they can be dismissed with Escape now that the
 * backdrop no longer closes them (which was discarding half-filled forms).
 */
export function useOnEscape(handler: () => void): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handler()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [handler])
}
