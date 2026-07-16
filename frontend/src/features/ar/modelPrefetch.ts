/**
 * AR model prefetching for the menu.
 *
 * One-tap-to-AR only works if the model is already in the browser cache when the
 * user taps — otherwise the (multi-MB) download pushes the AR launch outside the
 * browser's ~5 s user-activation window and the camera fails to start. So when the
 * menu mounts we warm the model-viewer library and prefetch the models for the
 * first few (visible) products immediately, then the rest during idle time.
 *
 * SPIKE (Step 0): every product currently uses the same hardcoded pizza model;
 * `productModelUrl()` is the single place to swap in per-product `model_glb_url`
 * once the backend provides it (M5).
 */

export const SPIKE_MODEL_URL = '/models/pizza.glb'
export const SPIKE_USDZ_URL = '/models/pizza.usdz' // iOS AR Quick Look source

/** Resolve a product's GLB url. SPIKE: same model for all. */
export function productModelUrl(): string {
  return SPIKE_MODEL_URL
}

const prefetched = new Set<string>()

/** Fetch a model into the HTTP cache once. Safe to call repeatedly. */
export function prefetchModel(url: string): void {
  if (prefetched.has(url)) return
  prefetched.add(url)
  fetch(url).catch(() => prefetched.delete(url)) // allow a retry if it failed
}

let libWarmed = false
/** Parse + register the model-viewer custom element ahead of the first tap. */
export function warmModelViewerLib(): void {
  if (libWarmed) return
  libWarmed = true
  import('@google/model-viewer').catch(() => {
    libWarmed = false
  })
}

const onIdle = (cb: () => void): void => {
  const ric = (window as unknown as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => void })
    .requestIdleCallback
  if (ric) ric(cb, { timeout: 4000 })
  else setTimeout(cb, 1500)
}

/**
 * Warm the lib, prefetch the first `immediate` distinct models now, and queue the
 * rest for idle time (staggered so they don't contend with the menu's own images).
 */
export function prefetchModelsProgressive(urls: string[], immediate = 4): void {
  warmModelViewerLib()
  const unique = [...new Set(urls)]
  unique.slice(0, immediate).forEach(prefetchModel)
  unique.slice(immediate).forEach((url, i) => {
    onIdle(() => setTimeout(() => prefetchModel(url), i * 400))
  })
}
