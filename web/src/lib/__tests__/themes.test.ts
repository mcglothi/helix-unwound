import { describe, expect, it } from 'vitest'
import { BUILTIN, contrast, parseBase16, tokens } from '../themes'

describe('base16 themes', () => {
  for (const sc of BUILTIN) {
    it(`${sc.name} stays readable`, () => {
      const t = tokens(sc)
      expect(contrast(t['--ink'], t['--bg'])).toBeGreaterThanOrEqual(7)
      expect(contrast(t['--muted'], t['--panel'])).toBeGreaterThanOrEqual(4.5)
      expect(contrast(t['--accent-ink'], t['--accent'])).toBeGreaterThanOrEqual(4.5)
      expect(contrast(t['--accent-text'], t['--panel'])).toBeGreaterThanOrEqual(4.5)
      for (const k of ['--c-sub', '--c-midbass', '--c-mid', '--c-tweeter', '--ok', '--warn'])
        expect(contrast(t[k], t['--panel'])).toBeGreaterThanOrEqual(3)
    })
  }

  it('parses classic base16 yaml', () => {
    const y = `scheme: "Test"\nauthor: "me"\n` + Array.from({ length: 16 }, (_, i) => `base0${i.toString(16).toUpperCase()}: "${i < 8 ? '1' : 'a'}${i.toString(16)}2030"`).join('\n')
    const sc = parseBase16(y)
    expect(sc.name).toBe('Test')
    expect(sc.palette.base0F).toBe('#af2030')
    expect(sc.variant).toBe('dark')
  })

  it('rejects incomplete schemes', () => {
    expect(() => parseBase16('base00: "000000"')).toThrow(/base01/)
  })
})
