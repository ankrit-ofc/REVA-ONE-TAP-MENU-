/**
 * Minimal ESC/POS encoder for 80 mm thermal printers (generic Xprinter-class).
 * Pure byte building — no dependency. Targets 48 columns (Font A on 80 mm).
 *
 * Only the commands we need for text receipts: init, alignment, bold,
 * double-size, line feed, paper cut. Non-ASCII characters degrade to '?' (we
 * stick to the printer's default single-byte code page rather than risk UTF-8
 * garbling).
 */

export const LINE_WIDTH = 48

const ESC = 0x1b
const GS = 0x1d
const LF = 0x0a

// Trailing feed before the cut, in printer dots (203 dpi → ~8 dots/mm). Covers the
// cutter-blade offset (~12 mm, so content isn't sliced) plus a ~2 cm visible tail.
// This is the one knob to tune per printer if the tail comes out short/long.
const TAIL_FEED_DOTS = 240

export class EscPos {
  private bytes: number[] = []

  /** ESC @ — reset to a known state. */
  init(): this {
    this.bytes.push(ESC, 0x40)
    return this
  }

  /** Append raw text (single-byte; non-ASCII → '?'). */
  text(s: string): this {
    for (let i = 0; i < s.length; i++) {
      const code = s.charCodeAt(i)
      this.bytes.push(code >= 0x20 && code <= 0x7e ? code : 0x3f)
    }
    return this
  }

  /** Append text followed by a line feed. */
  line(s = ''): this {
    return this.text(s).feed(1)
  }

  /** ESC a n — 0 left, 1 center, 2 right. */
  align(a: 'left' | 'center' | 'right'): this {
    const n = a === 'center' ? 1 : a === 'right' ? 2 : 0
    this.bytes.push(ESC, 0x61, n)
    return this
  }

  /** ESC E n — emphasis (bold) on/off. */
  bold(on: boolean): this {
    this.bytes.push(ESC, 0x45, on ? 1 : 0)
    return this
  }

  /** GS ! n — character size; double = both width & height. */
  size(scale: 'normal' | 'double'): this {
    this.bytes.push(GS, 0x21, scale === 'double' ? 0x11 : 0x00)
    return this
  }

  feed(n = 1): this {
    for (let i = 0; i < n; i++) this.bytes.push(LF)
    return this
  }

  /**
   * Feed an exact number of printer dots (ESC J n, n = 0..255 → n/203 inch).
   * Dot-based so the distance is independent of the current line spacing; chains
   * multiple commands when more than 255 dots are requested.
   */
  feedDots(dots: number): this {
    let remaining = Math.max(0, Math.round(dots))
    while (remaining > 0) {
      const n = Math.min(255, remaining)
      this.bytes.push(ESC, 0x4a, n) // ESC J n — print and feed n dots
      remaining -= n
    }
    return this
  }

  /** A full-width dashed divider line. */
  divider(): this {
    return this.line('-'.repeat(LINE_WIDTH))
  }

  /**
   * Left text + right text on one line, right-aligned within LINE_WIDTH.
   * Left is truncated if the two would overlap.
   */
  twoCol(left: string, right: string): this {
    const space = LINE_WIDTH - right.length
    let l = left
    if (l.length > space - 1) l = l.slice(0, Math.max(0, space - 1))
    const pad = LINE_WIDTH - l.length - right.length
    return this.line(l + ' '.repeat(Math.max(1, pad)) + right)
  }

  /**
   * End the receipt: feed a deterministic ~2 cm tail past the content, then partial-cut
   * at the current position. Uses a dot-based feed + `GS V 1` ("cut here") rather than
   * `GS V 66 n` ("feed to cutting position then cut") — the latter makes many generic POS
   * printers over-feed toward a page/label boundary, leaving a long blank before the cut.
   */
  cut(): this {
    this.feedDots(TAIL_FEED_DOTS)
    this.bytes.push(GS, 0x56, 0x01) // GS V 1 — partial cut at current position (no page feed)
    return this
  }

  build(): Uint8Array {
    return new Uint8Array(this.bytes)
  }
}
