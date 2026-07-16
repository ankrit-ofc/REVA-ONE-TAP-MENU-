// Type declaration for Google's <model-viewer> web component so it can be used
// as a JSX element under strict TypeScript. Only the attributes we actually use
// are typed; add more here if the viewer grows. The element itself is registered
// at runtime by `import('@google/model-viewer')` (lazy-loaded in TableArView).
import type React from 'react'

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'model-viewer': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string
          'ios-src'?: string
          alt?: string
          poster?: string
          loading?: 'auto' | 'lazy' | 'eager'
          'camera-controls'?: boolean
          'auto-rotate'?: boolean
          ar?: boolean
          'ar-modes'?: string
          'ar-scale'?: string
          'ar-placement'?: 'floor' | 'wall'
          'shadow-intensity'?: string | number
          exposure?: string | number
          'touch-action'?: string
        },
        HTMLElement
      >
    }
  }
}
