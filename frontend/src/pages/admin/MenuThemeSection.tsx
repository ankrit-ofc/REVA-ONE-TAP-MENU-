import { useState } from 'react'
import { MENU_TEMPLATES, HEX_COLOR_PATTERN, type MenuTemplate, type ProductPublic } from '@/lib/schemas/menu'
import { resolveMenuTemplate } from '@/features/menu/templates'
import { deriveMenuTheme, type MenuThemeMode } from '@/lib/menuAccent'
import styles from './MenuThemeSection.module.css'

export const DEFAULT_MENU_ACCENT = '#1b4332'

const TEMPLATE_LABEL: Record<MenuTemplate, string> = {
  classic: 'Classic',
  photo_grid: 'Photo grid',
  elegant_list: 'Elegant list',
  compact_list: 'Compact list',
  magazine: 'Magazine',
  bold_cards: 'Bold cards',
}

const TEMPLATE_HINT: Record<MenuTemplate, string> = {
  classic: 'Thumbnail-left cards — how your menu looks today. The default.',
  photo_grid: 'Two-column cards, large images.',
  elegant_list: 'Serif, no photos — name and price on one line.',
  compact_list: 'Tiny thumbnail, name, price. Flat and dense — built for big menus.',
  magazine: 'A hero photo for the first item in each category, rest as a list.',
  bold_cards: 'Full-width cards with your accent colour as a tinted block.',
}

// Illustrative sample data for the live preview — never sent to the backend.
// Deliberately includes a no-image item and a long name/description so admins
// see how the chosen template handles both before saving.
const PREVIEW_PRODUCTS: ProductPublic[] = [
  {
    id: 'preview-1',
    name: 'Chef’s Signature Grilled Chicken Platter',
    description: 'Char-grilled chicken thigh marinated overnight in smoked paprika, garlic, and citrus, served with roasted seasonal vegetables and herbed rice.',
    base_price: 650,
    tax_rate: 0,
    food_type: 'NON_VEG',
    image_url: null,
    has_variants: false,
    allows_addons: false,
    variants: [],
    addons: [],
    model_glb_url: null,
    model_usdz_url: null,
  },
  {
    id: 'preview-2',
    name: 'Paneer Tikka Wrap',
    description: 'Cottage cheese, mint chutney, and crisp veggies in a warm flatbread.',
    base_price: 320,
    tax_rate: 0,
    food_type: 'VEG',
    image_url: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="150"%3E%3Crect width="200" height="150" fill="%23d7e8dd"/%3E%3C/svg%3E',
    has_variants: false,
    allows_addons: false,
    variants: [],
    addons: [],
    model_glb_url: null,
    model_usdz_url: null,
  },
  {
    id: 'preview-3',
    name: 'Masala Chai',
    description: null,
    base_price: 90,
    tax_rate: 0,
    food_type: 'BEVERAGE',
    image_url: null,
    has_variants: false,
    allows_addons: false,
    variants: [],
    addons: [],
    model_glb_url: null,
    model_usdz_url: null,
  },
]

interface Props {
  template: MenuTemplate
  accentColor: string | null
  onTemplateChange: (template: MenuTemplate) => void
  onAccentColorChange: (color: string) => void
}

export default function MenuThemeSection({ template, accentColor, onTemplateChange, onAccentColorChange }: Props) {
  const [previewMode, setPreviewMode] = useState<MenuThemeMode>('light')
  const wheelValue = HEX_COLOR_PATTERN.test(accentColor ?? '') ? (accentColor as string) : DEFAULT_MENU_ACCENT
  const validColor = HEX_COLOR_PATTERN.test(accentColor ?? '') ? accentColor : DEFAULT_MENU_ACCENT
  const PreviewTemplate = resolveMenuTemplate(template)

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>Edit menu</h2>
      <p className={styles.hint}>
        Choose how the customer-facing menu looks. Changes apply after you save.
      </p>

      <div className={styles.thumbGrid} role="radiogroup" aria-label="Menu template">
        {MENU_TEMPLATES.map((t) => (
          <button
            key={t}
            type="button"
            role="radio"
            aria-checked={template === t}
            className={`${styles.thumbBtn} ${template === t ? styles.thumbBtnActive : ''}`}
            onClick={() => onTemplateChange(t)}
          >
            <Thumbnail template={t} />
            <span className={styles.thumbLabel}>{TEMPLATE_LABEL[t]}</span>
          </button>
        ))}
      </div>
      <p className={styles.hint}>{TEMPLATE_HINT[template]}</p>

      <div className={styles.colorRow}>
        <label className={styles.colorField}>
          <span className={styles.fieldLabel}>Accent colour</span>
          <input
            type="color"
            className={styles.colorWheel}
            value={wheelValue}
            onChange={(e) => onAccentColorChange(e.target.value)}
            aria-label="Accent colour picker"
          />
        </label>
        <label className={styles.colorField}>
          <span className={styles.fieldLabel}>Hex</span>
          <input
            type="text"
            className={styles.hexInput}
            value={accentColor ?? ''}
            placeholder={DEFAULT_MENU_ACCENT}
            maxLength={7}
            onChange={(e) => onAccentColorChange(e.target.value)}
            aria-label="Accent colour hex code"
          />
        </label>
      </div>
      {accentColor && !HEX_COLOR_PATTERN.test(accentColor) && (
        <p className={styles.err}>Hex colour must look like #1D9E75.</p>
      )}

      <div className={styles.previewLabelRow}>
        <span className={styles.previewLabel}>Live preview</span>
        <div className={styles.themeToggle} role="radiogroup" aria-label="Preview theme">
          <button
            type="button"
            role="radio"
            aria-checked={previewMode === 'light'}
            className={`${styles.themeToggleBtn} ${previewMode === 'light' ? styles.themeToggleBtnActive : ''}`}
            onClick={() => setPreviewMode('light')}
          >
            Light
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={previewMode === 'dark'}
            className={`${styles.themeToggleBtn} ${previewMode === 'dark' ? styles.themeToggleBtnActive : ''}`}
            onClick={() => setPreviewMode('dark')}
          >
            Dark
          </button>
        </div>
      </div>
      {/* stopPropagation in the capture phase neutralises the template's tap-to-open
          navigation — this is a preview, not a live menu, and must never route away
          from Settings. */}
      <div
        className={styles.preview}
        data-theme={previewMode}
        style={deriveMenuTheme(validColor, previewMode)}
        onClickCapture={(e) => e.stopPropagation()}
        onKeyDownCapture={(e) => e.stopPropagation()}
      >
        <div className={styles.previewBar}>
          <span className={styles.previewBrand}>REVA</span>
          <span className={styles.previewCartBadge}>2</span>
        </div>
        <div className={styles.previewSpecials}>⭐ Today&rsquo;s Special</div>
        <div className={styles.previewChipRow}>
          <span className={styles.previewChipActive}>All</span>
          <span className={styles.previewChip}>Mains</span>
          <span className={styles.previewChip}>Non-veg</span>
        </div>
        <PreviewTemplate products={PREVIEW_PRODUCTS} currency="NPR" />
      </div>
    </section>
  )
}

/** Abstract layout glyph — shows the shape of each template without needing
 *  real screenshots. */
function Thumbnail({ template }: { template: MenuTemplate }) {
  switch (template) {
    case 'classic':
      return (
        <svg viewBox="0 0 64 48" className={styles.thumbSvg} aria-hidden="true">
          <rect x="2" y="2" width="12" height="20" rx="1" fill="currentColor" opacity="0.4" />
          <rect x="17" y="5" width="14" height="4" rx="1" fill="currentColor" opacity="0.7" />
          <rect x="17" y="15" width="14" height="4" rx="1" fill="currentColor" opacity="0.5" />
          <rect x="35" y="2" width="12" height="20" rx="1" fill="currentColor" opacity="0.4" />
          <rect x="50" y="5" width="12" height="4" rx="1" fill="currentColor" opacity="0.7" />
          <rect x="50" y="15" width="12" height="4" rx="1" fill="currentColor" opacity="0.5" />
        </svg>
      )
    case 'photo_grid':
      return (
        <svg viewBox="0 0 64 48" className={styles.thumbSvg} aria-hidden="true">
          <rect x="2" y="2" width="27" height="20" rx="2" fill="currentColor" opacity="0.35" />
          <rect x="2" y="24" width="27" height="6" rx="1" fill="currentColor" opacity="0.6" />
          <rect x="35" y="2" width="27" height="20" rx="2" fill="currentColor" opacity="0.35" />
          <rect x="35" y="24" width="27" height="6" rx="1" fill="currentColor" opacity="0.6" />
        </svg>
      )
    case 'elegant_list':
      return (
        <svg viewBox="0 0 64 48" className={styles.thumbSvg} aria-hidden="true">
          {[6, 18, 30, 42].map((y) => (
            <g key={y}>
              <rect x="2" y={y} width="34" height="4" rx="1" fill="currentColor" opacity="0.7" />
              <rect x="52" y={y} width="10" height="4" rx="1" fill="currentColor" opacity="0.45" />
            </g>
          ))}
        </svg>
      )
    case 'compact_list':
      return (
        <svg viewBox="0 0 64 48" className={styles.thumbSvg} aria-hidden="true">
          {[1, 8, 15, 22, 29, 36, 43].map((y) => (
            <g key={y}>
              <rect x="2" y={y} width="4" height="4" rx="1" fill="currentColor" opacity="0.4" />
              <rect x="9" y={y + 1} width="38" height="2" rx="1" fill="currentColor" opacity="0.7" />
              <rect x="52" y={y + 1} width="10" height="2" rx="1" fill="currentColor" opacity="0.5" />
            </g>
          ))}
        </svg>
      )
    case 'magazine':
      return (
        <svg viewBox="0 0 64 48" className={styles.thumbSvg} aria-hidden="true">
          <rect x="2" y="2" width="60" height="18" rx="2" fill="currentColor" opacity="0.4" />
          <rect x="2" y="23" width="60" height="4" rx="1" fill="currentColor" opacity="0.65" />
          <rect x="2" y="30" width="60" height="4" rx="1" fill="currentColor" opacity="0.65" />
          <rect x="2" y="37" width="60" height="4" rx="1" fill="currentColor" opacity="0.65" />
        </svg>
      )
    case 'bold_cards':
      return (
        <svg viewBox="0 0 64 48" className={styles.thumbSvg} aria-hidden="true">
          <rect x="2" y="2" width="60" height="13" rx="2" fill="currentColor" opacity="0.3" />
          <rect x="2" y="18" width="60" height="13" rx="2" fill="currentColor" opacity="0.3" />
          <rect x="2" y="34" width="60" height="13" rx="2" fill="currentColor" opacity="0.3" />
        </svg>
      )
  }
}
