// Base16 theming. A scheme's 16 colours map onto the app's semantic tokens; contrast is
// checked and corrected so any scheme stays readable.
//
// base00 background · base01 panels · base02 lines/selection · base03 dim text
// base04 muted text · base05 text · base06/07 bright text
// base08 red · base09 orange · base0A yellow · base0B green · base0C cyan · base0D blue
// base0E purple · base0F brown

export type Base16Key =
  | 'base00' | 'base01' | 'base02' | 'base03' | 'base04' | 'base05' | 'base06' | 'base07'
  | 'base08' | 'base09' | 'base0A' | 'base0B' | 'base0C' | 'base0D' | 'base0E' | 'base0F'

export interface Scheme {
  name: string
  author?: string
  variant: 'dark' | 'light'
  palette: Record<Base16Key, string> // '#rrggbb'
  accent?: Base16Key                 // which colour is the app accent (default base0A)
  builtin?: boolean
}

const KEYS: Base16Key[] = ['base00', 'base01', 'base02', 'base03', 'base04', 'base05', 'base06', 'base07',
  'base08', 'base09', 'base0A', 'base0B', 'base0C', 'base0D', 'base0E', 'base0F']

const s = (name: string, variant: 'dark' | 'light', hex: string, extra: Partial<Scheme> = {}): Scheme => {
  const vals = hex.trim().split(/\s+/)
  return { name, variant, builtin: true, palette: Object.fromEntries(KEYS.map((k, i) => [k, '#' + vals[i]])) as Scheme['palette'], ...extra }
}

export const BUILTIN: Scheme[] = [
  s('Studio', 'dark', '121417 181b1f 2a2e34 8d8a83 a8a49b ebe7df f4f1ea ffffff ff8f7a ff7a59 f2b84b 5cc98f 4fd1c5 5aa9ff b48cff c98a5a',
    { author: 'HelixTune' }),
  s('Studio Light', 'light', 'f4f5f7 ffffff dfe2e7 6b7380 4f5662 12161c 0b0e12 000000 c4382a c25a1b 9a6a00 1d7a45 0f7d86 1f5fd1 6b3fc2 8a5a2b',
    { author: 'HelixTune' }),
  s('Night', 'dark', '000000 0b0f12 1a2228 6f808c 9fb0bd e6edf2 f2f6f9 ffffff ff6b6b ff8a4c ffb547 7ee0a0 38d3ff 4fb2ff b68cff c98a5a',
    { author: 'HelixTune', accent: 'base0C' }),
  s('Tomorrow Night', 'dark', '1d1f21 282a2e 373b41 969896 b4b7b4 c5c8c6 e0e0e0 ffffff cc6666 de935f f0c674 b5bd68 8abeb7 81a2be b294bb a3685a',
    { author: 'Chris Kempson' }),
  s('Gruvbox Dark', 'dark', '282828 3c3836 504945 665c54 bdae93 d5c4a1 ebdbb2 fbf1c7 fb4934 fe8019 fabd2f b8bb26 8ec07c 83a598 d3869b d65d0e',
    { author: 'Pavel Pertsev' }),
  s('Nord', 'dark', '2e3440 3b4252 434c5e 4c566a d8dee9 e5e9f0 eceff4 8fbcbb bf616a d08770 ebcb8b a3be8c 88c0d0 81a1c1 b48ead 5e81ac',
    { author: 'arcticicestudio', accent: 'base0C' }),
  s('Solarized Dark', 'dark', '002b36 073642 586e75 657b83 839496 93a1a1 eee8d5 fdf6e3 dc322f cb4b16 b58900 859900 2aa198 268bd2 6c71c4 d33682',
    { author: 'Ethan Schoonover' }),
  s('Solarized Light', 'light', 'fdf6e3 eee8d5 93a1a1 839496 657b83 586e75 073642 002b36 dc322f cb4b16 b58900 859900 2aa198 268bd2 6c71c4 d33682',
    { author: 'Ethan Schoonover' }),
  s('Monokai', 'dark', '272822 383830 49483e 75715e a59f85 f8f8f2 f5f4f1 f9f8f5 f92672 fd971f f4bf75 a6e22e a1efe4 66d9ef ae81ff cc6633',
    { author: 'Wimer Hazenberg' }),
  s('One Dark', 'dark', '282c34 353b45 3e4451 545862 565c64 abb2bf b6bdca c8ccd4 e06c75 d19a66 e5c07b 98c379 56b6c2 61afef c678dd be5046',
    { author: 'Lalit Magant', accent: 'base0D' }),
]

// ---- colour math ---------------------------------------------------------------------------

type RGB = [number, number, number]
const toRgb = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB
const toHex = (c: RGB) => '#' + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('')
const mix = (a: string, b: string, t: number) => {
  const A = toRgb(a), B = toRgb(b)
  return toHex([0, 1, 2].map((i) => A[i] + (B[i] - A[i]) * t) as RGB)
}
const lum = (h: string) => {
  const [r, g, b] = toRgb(h).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
export const contrast = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
/** Move `fg` toward `toward` until it reaches `ratio` against `bg`. */
function ensure(fg: string, bg: string, toward: string, ratio: number) {
  let c = fg
  for (let t = 0; t <= 1.0001 && contrast(c, bg) < ratio; t += 0.05) c = mix(fg, toward, t)
  return c
}

/** Readable text colour on a filled `bg`: a deep tint of it if possible, else white or black. */
function onColor(bg: string) {
  const tint = mix(bg, '#000000', 0.8)
  if (contrast(tint, bg) >= 4.5 && contrast(tint, bg) >= contrast('#ffffff', bg)) return tint
  if (contrast('#ffffff', bg) >= 4.5) return '#ffffff'
  return contrast('#000000', bg) >= contrast('#ffffff', bg) ? '#000000' : '#ffffff'
}

/** Semantic tokens for a scheme (what the CSS uses). */
export function tokens(sc: Scheme): Record<string, string> {
  const p = sc.palette
  const bg = p.base00
  const ink = ensure(p.base05, bg, sc.variant === 'dark' ? '#ffffff' : '#000000', 7)
  const accent = p[sc.accent ?? 'base0A']
  const panel = p.base01 === bg ? mix(bg, ink, 0.04) : p.base01
  const t = {
    '--bg': bg,
    '--panel': panel,
    '--panel-2': mix(panel, p.base02, 0.45),
    '--line': p.base02,
    '--line-2': mix(p.base02, p.base03, 0.45),
    '--ink': ink,
    '--muted': ensure(p.base04, panel, ink, 4.5),
    '--dim': ensure(p.base03, panel, ink, 3),
    '--accent': accent,
    '--accent-ink': onColor(accent),
    '--accent-text': ensure(accent, panel, ink, 4.5),
    '--ok': ensure(p.base0B, panel, ink, 3),
    '--warn': ensure(p.base08, panel, ink, 3),
    '--c-sub': ensure(p.base0E, panel, ink, 3),
    '--c-midbass': ensure(p.base09, panel, ink, 3),
    '--c-mid': ensure(p.base0B, panel, ink, 3),
    '--c-tweeter': ensure(p.base0D, panel, ink, 3),
    '--c-full': ensure(p.base0C, panel, ink, 3),
    '--toast-err-bg': mix(panel, p.base08, 0.35),
    '--toast-ok-bg': mix(panel, p.base0B, 0.3),
  }
  return t
}

export function applyScheme(sc: Scheme, root: HTMLElement = document.documentElement) {
  for (const [k, v] of Object.entries(tokens(sc))) root.style.setProperty(k, v)
  root.style.colorScheme = sc.variant
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', sc.palette.base00)
}

/** Parse a base16 scheme in YAML (classic `base00: "282828"` or tinted-theming `palette:` form). */
export function parseBase16(text: string): Scheme {
  const get = (k: string) => text.match(new RegExp(`^\\s*${k}\\s*:\\s*["']?#?([0-9a-fA-F]{6})["']?`, 'm'))?.[1]
  const meta = (k: string) => text.match(new RegExp(`^\\s*${k}\\s*:\\s*["']?([^"'\\n]+)["']?`, 'm'))?.[1]?.trim()
  const palette = {} as Scheme['palette']
  for (const k of KEYS) {
    const v = get(k)
    if (!v) throw new Error(`missing ${k}`)
    palette[k] = '#' + v.toLowerCase()
  }
  const variant = (meta('variant') === 'light' || lum(palette.base00) > 0.4) ? 'light' : 'dark'
  return { name: meta('(?:scheme|name)') ?? 'Imported', author: meta('author'), variant, palette }
}
