// Client-side EQ magnitude for instant drag feedback. Same RBJ formulas as the engine
// (src/helixtune/dsp/filters.py); the engine remains authoritative.

import type { EqBand } from './types'

interface BQ { b0: number; b1: number; b2: number; a1: number; a2: number }

function biquad(b: EqBand, fs: number): BQ | null {
  if (!b.enabled) return null
  if (b.gain_db === 0 && (b.type === 'peak' || b.type === 'low_shelf' || b.type === 'high_shelf')) return null
  const A = 10 ** (b.gain_db / 40)
  const w0 = (2 * Math.PI * b.freq_hz) / fs
  const cw = Math.cos(w0), sw = Math.sin(w0)
  const al = sw / (2 * b.q)
  const n = (b0: number, b1: number, b2: number, a0: number, a1: number, a2: number): BQ =>
    ({ b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 })
  switch (b.type) {
    case 'peak': return n(1 + al * A, -2 * cw, 1 - al * A, 1 + al / A, -2 * cw, 1 - al / A)
    case 'notch': return n(1, -2 * cw, 1, 1 + al, -2 * cw, 1 - al)
    case 'allpass': return n(1 - al, -2 * cw, 1 + al, 1 + al, -2 * cw, 1 - al)
    case 'low_shelf': {
      const s = 2 * Math.sqrt(A) * al
      return n(A * (A + 1 - (A - 1) * cw + s), 2 * A * (A - 1 - (A + 1) * cw), A * (A + 1 - (A - 1) * cw - s),
        A + 1 + (A - 1) * cw + s, -2 * (A - 1 + (A + 1) * cw), A + 1 + (A - 1) * cw - s)
    }
    case 'high_shelf': {
      const s = 2 * Math.sqrt(A) * al
      return n(A * (A + 1 + (A - 1) * cw + s), -2 * A * (A - 1 + (A + 1) * cw), A * (A + 1 + (A - 1) * cw - s),
        A + 1 - (A - 1) * cw + s, 2 * (A - 1 - (A + 1) * cw), A + 1 - (A - 1) * cw - s)
    }
  }
}

function magDb(q: BQ, f: number, fs: number): number {
  const w = (2 * Math.PI * f) / fs
  const c1 = Math.cos(w), s1 = Math.sin(w), c2 = Math.cos(2 * w), s2 = Math.sin(2 * w)
  const nr = q.b0 + q.b1 * c1 + q.b2 * c2, ni = -(q.b1 * s1 + q.b2 * s2)
  const dr = 1 + q.a1 * c1 + q.a2 * c2, di = -(q.a1 * s1 + q.a2 * s2)
  return 10 * Math.log10((nr * nr + ni * ni) / (dr * dr + di * di))
}

export function eqCurve(bands: EqBand[], freqs: number[], fs = 96000): number[] {
  const qs = bands.map((b) => biquad(b, fs)).filter((x): x is BQ => x !== null)
  return freqs.map((f) => qs.reduce((acc, q) => acc + magDb(q, f, fs), 0))
}

export const logFreqs = (n = 300, lo = 20, hi = 20000) =>
  Array.from({ length: n }, (_, i) => lo * (hi / lo) ** (i / (n - 1)))

export const fmtHz = (f: number) => (f >= 1000 ? `${+(f / 1000).toFixed(f >= 10000 ? 1 : 2)}k` : `${Math.round(f)}`)
export const fmtDb = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(1)}`
