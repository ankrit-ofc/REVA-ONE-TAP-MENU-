import { useState } from 'react'
import Button from '@/components/common/Button'
import styles from './ItemNoteEditor.module.css'

export const NOTE_PRESET_CHIPS = [
  'Less spicy',
  'Extra spicy',
  'No onion',
  'No garlic',
  'Less oil',
]

export const NOTE_MAX_LENGTH = 140

/** Best-effort split of a stored note back into known chips + free text, so
 * reopening the editor restores which chips were selected. */
function parseNote(note: string): { chips: string[]; freeText: string } {
  const tokens = note.split(',').map((t) => t.trim()).filter(Boolean)
  const chips = NOTE_PRESET_CHIPS.filter((chip) => tokens.includes(chip))
  const freeText = tokens.filter((t) => !NOTE_PRESET_CHIPS.includes(t)).join(', ')
  return { chips, freeText }
}

function composeNote(chips: string[], freeText: string): string {
  return [...chips, freeText.trim()].filter(Boolean).join(', ').slice(0, NOTE_MAX_LENGTH)
}

interface Props {
  value: string
  onSave: (note: string) => void
  onCancel: () => void
}

export default function ItemNoteEditor({ value, onSave, onCancel }: Props) {
  const initial = parseNote(value)
  const [chips, setChips] = useState<string[]>(initial.chips)
  const [freeText, setFreeText] = useState(initial.freeText)

  const composed = composeNote(chips, freeText)

  function toggleChip(chip: string) {
    setChips((prev) => (prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip]))
  }

  function handleFreeTextChange(text: string) {
    const chipsPrefix = chips.length > 0 ? `${chips.join(', ')}, ` : ''
    const budget = Math.max(0, NOTE_MAX_LENGTH - chipsPrefix.length)
    setFreeText(text.slice(0, budget))
  }

  return (
    <div className={styles.panel}>
      <p className={styles.caption}>Special requests — no extra items</p>

      <div className={styles.chips}>
        {NOTE_PRESET_CHIPS.map((chip) => (
          <button
            key={chip}
            type="button"
            className={`${styles.chip} ${chips.includes(chip) ? styles.chipSelected : ''}`}
            aria-pressed={chips.includes(chip)}
            onClick={() => toggleChip(chip)}
          >
            {chip}
          </button>
        ))}
      </div>

      <textarea
        className={styles.textarea}
        value={freeText}
        onChange={(e) => handleFreeTextChange(e.target.value)}
        placeholder="Add a note (optional)"
        rows={2}
      />

      <div className={styles.footer}>
        <span className={styles.counter}>
          {composed.length}/{NOTE_MAX_LENGTH}
        </span>
        <div className={styles.actions}>
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={() => onSave(composed)}>
            Save
          </Button>
        </div>
      </div>
    </div>
  )
}
