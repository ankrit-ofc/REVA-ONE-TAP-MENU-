/**
 * Loud, attention-grabbing notification chimes synthesized with the Web Audio API.
 * No audio asset and no dependencies — works offline.
 *
 * Browser autoplay policy: an AudioContext starts *suspended* and may only be
 * resumed in response to a user gesture. Alerts are triggered by WebSocket events
 * (not a gesture), so `primeNotificationAudio()` unlocks the context on the staff
 * member's first interaction, and `unlockAudioNow()` does it explicitly from the
 * "Sound alerts" toggle. `playChime()` can then fire later from a realtime handler.
 */

let ctx: AudioContext | null = null
let primed = false

type WindowWithWebkitAudio = Window &
  typeof globalThis & { webkitAudioContext?: typeof AudioContext }

function getContext(): AudioContext | null {
  if (ctx) return ctx
  const w = window as WindowWithWebkitAudio
  const Ctor = w.AudioContext ?? w.webkitAudioContext
  if (!Ctor) return null // Web Audio unsupported → silently skip
  ctx = new Ctor()
  return ctx
}

/** One short beep: oscillator → gain envelope, scheduled at absolute time `start`. */
function beep(
  audio: AudioContext,
  freq: number,
  start: number,
  duration: number,
  peak: number,
): void {
  const osc = audio.createOscillator()
  const gain = audio.createGain()
  osc.type = 'square' // richer/harsher than sine → cuts through noise
  osc.frequency.setValueAtTime(freq, start)

  // Quick attack + exponential decay avoids clicks while staying loud.
  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(peak, start + 0.01)
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)

  osc.connect(gain)
  gain.connect(audio.destination)
  osc.start(start)
  osc.stop(start + duration + 0.02)
}

/** A chime is a sequence of tones at offsets (seconds) from the chime's start. */
export type ChimePattern = ReadonlyArray<{ freq: number; at: number; dur: number }>

// Three audibly distinct chimes so staff know the alert type by ear.
export const CHIME_NEW_ORDER: ChimePattern = [
  { freq: 784, at: 0, dur: 0.15 },     // G5  ─┐ quick rising "ding-ding"
  { freq: 1047, at: 0.18, dur: 0.22 }, // C6  ─┘
]
export const CHIME_READY: ChimePattern = [
  { freq: 1319, at: 0, dur: 0.14 },    // E6  high-low-high "ta-da-da"
  { freq: 988, at: 0.18, dur: 0.14 },  // B5
  { freq: 1319, at: 0.36, dur: 0.26 }, // E6
]
export const CHIME_BILL: ChimePattern = [
  { freq: 880, at: 0, dur: 0.18 },     // A5  rising 3-tone (the original bill chime)
  { freq: 1175, at: 0.2, dur: 0.18 },  // D6
  { freq: 1568, at: 0.4, dur: 0.3 },   // G6
]
export const CHIME_WAITER: ChimePattern = [
  { freq: 1047, at: 0, dur: 0.18 },    // C6  descending "ding-dong" doorbell
  { freq: 784, at: 0.22, dur: 0.3 },   // G5
]

const PEAK = 0.9 // high gain → loud
const REPEAT_GAP = 0.35 // silence between repeats (seconds)

function patternDuration(pattern: ChimePattern): number {
  return pattern.reduce((max, t) => Math.max(max, t.at + t.dur), 0)
}

/**
 * Plays a chime `repeats` times back-to-back (default 3), all scheduled up front on
 * the audio timeline so it self-stops — no timers, no manual acknowledge needed.
 * Safe to call from anywhere; no-ops if Web Audio is unavailable.
 */
export function playChime(pattern: ChimePattern, repeats = 3): void {
  const audio = getContext()
  if (!audio) return
  // Defensive resume in case the context drifted back to suspended.
  void audio.resume().catch(() => {})

  const dur = patternDuration(pattern)
  const base = audio.currentTime
  for (let i = 0; i < repeats; i++) {
    const offset = base + i * (dur + REPEAT_GAP)
    for (const t of pattern) beep(audio, t.freq, offset + t.at, t.dur, PEAK)
  }
}

/**
 * Explicitly unlock audio from a user gesture (the "Sound alerts" toggle) and play
 * one short confirmation beep so staff hear that sound is working.
 */
export function unlockAudioNow(): void {
  const audio = getContext()
  if (!audio) return
  void audio.resume().catch(() => {})
  beep(audio, 1175, audio.currentTime + 0.01, 0.12, 0.5)
}

/**
 * Idempotently registers one-time gesture listeners that create and resume the
 * AudioContext, unlocking later programmatic playback under autoplay policy.
 * Returns a cleanup function that removes the listeners if still pending.
 */
export function primeNotificationAudio(): () => void {
  if (primed) return () => {}
  primed = true

  const unlock = () => {
    const audio = getContext()
    if (audio && audio.state === 'suspended') void audio.resume().catch(() => {})
    remove()
  }
  const remove = () => {
    document.removeEventListener('pointerdown', unlock)
    document.removeEventListener('keydown', unlock)
  }

  document.addEventListener('pointerdown', unlock, { once: true })
  document.addEventListener('keydown', unlock, { once: true })
  return remove
}
