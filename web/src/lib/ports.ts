// Typed ports per component kind. Handles on the canvas are generated from these, and
// they decide which wires are allowed (same signal type, output -> input).

import type { Component, Signal, Tune } from './types'

export type Dir = 'in' | 'out'
export interface Port { id: string; label: string; signal: Signal; dir: Dir; multi?: boolean; group: 'main' | 'power' }

const P = (id: string, label: string, signal: Signal, dir: Dir, extra: Partial<Port> = {}): Port =>
  ({ id, label, signal, dir, group: signal === 'power' || signal === 'ground' || signal === 'remote' ? 'power' : 'main', ...extra })

const powerIn = [P('p12', '+12 V', 'power', 'in'), P('gnd', 'GND', 'ground', 'in'), P('rem', 'REM', 'remote', 'in')]

export function portsFor(c: Component, tune: Tune | null): Port[] {
  const n = (k: string, d: number) => {
    const v = Number(c.specs[k]?.value)
    return Number.isFinite(v) && v > 0 && v <= 16 ? Math.round(v) : d
  }
  switch (c.kind) {
    case 'source':
      return [P('spk', 'Speaker out', 'high_level', 'out', { multi: true }), P('rca', 'RCA out', 'line', 'out', { multi: true }),
        P('data', 'Data', 'data', 'out', { multi: true }),
        P('opt', 'Optical out', 'optical', 'out'), P('p12', '+12 V', 'power', 'in'), P('gnd', 'GND', 'ground', 'in'),
        P('remo', 'REM out', 'remote', 'out', { multi: true })]
    case 'interface':
      return [P('data', 'Vehicle data', 'data', 'in', { multi: true }), P('hlin', 'Speaker in', 'high_level', 'in', { multi: true }),
        P('opt', 'Optical out', 'optical', 'out'), P('rca', 'RCA out', 'line', 'out', { multi: true }), ...powerIn]
    case 'controller':
      return [P('data', 'Control', 'data', 'out')]
    case 'dsp': {
      const outs = (tune?.channels ?? []).map((ch) => P(`out${ch.id}`, `${ch.id}${ch.name ? ' · ' + ch.name : ''}`, 'line', 'out', { multi: true }))
      return [P('hl', 'High-level in', 'high_level', 'in', { multi: true }), P('rcain', 'RCA in', 'line', 'in', { multi: true }),
        P('optin', 'Optical in', 'optical', 'in'), P('usb', 'USB', 'usb', 'in'), P('ctl', 'Controller', 'data', 'in'), ...outs, ...powerIn,
        P('remo', 'REM out', 'remote', 'out', { multi: true })]
    }
    case 'amplifier': {
      const k = n('channels', 4)
      if (String(c.specs.mode?.value ?? '').toLowerCase().startsWith('bridge') && k >= 2) {
        // bridged pairs: 1+2, 3+4, … each pair is one channel fed by one input
        const pairs = Math.floor(k / 2)
        const names = pairs === 2 ? ['L', 'R'] : Array.from({ length: pairs }, (_, i) => `${i + 1}`)
        return [
          ...names.map((nm, i) => P(`in${nm}`, `In ${nm}`, 'line', 'in')),
          ...names.map((nm, i) => P(`out${2 * i + 1}${2 * i + 2}`, `Out ${2 * i + 1}+${2 * i + 2} (bridged)`, 'speaker', 'out', { multi: true })),
          ...powerIn,
        ]
      }
      const ins = Array.from({ length: k }, (_, i) => P(`in${i + 1}`, `In ${i + 1}`, 'line', 'in'))
      const outs = Array.from({ length: k }, (_, i) => P(`out${i + 1}`, `Out ${i + 1}`, 'speaker', 'out', { multi: true }))
      return [...ins, ...outs, ...powerIn]
    }
    case 'speaker':
    case 'subwoofer':
      return [P('in', 'Speaker in', 'speaker', 'in', { multi: true })]
    case 'microphone':
      return [P('usb', 'USB', 'usb', 'out')]
    case 'power':
      return [P('p12', '+12 V', 'power', 'out', { multi: true }), P('gnd', 'GND', 'ground', 'out', { multi: true })]
    case 'computer':
      return [P('usb', 'USB', 'usb', 'out', { multi: true }), P('usbin', 'USB in', 'usb', 'in', { multi: true }),
        P('p12', '+12 V', 'power', 'in'), P('gnd', 'GND', 'ground', 'in')]
    case 'enclosure':
      return []
    default:
      return [P('in', 'In', 'other', 'in', { multi: true }), P('out', 'Out', 'other', 'out', { multi: true })]
  }
}

export const handleId = (p: Port) => `${p.dir}:${p.id}`
export const parseHandle = (h: string | null | undefined) => {
  const [dir, id] = (h ?? '').split(':')
  return { dir: dir as Dir, id }
}

/** Which component kinds could accept a wire dragged from this port (for the drop-to-add menu). */
export function compatibleKinds(p: Port): Component['kind'][] {
  const want: Dir = p.dir === 'out' ? 'in' : 'out'
  const kinds: Component['kind'][] = ['source', 'interface', 'dsp', 'controller', 'amplifier', 'speaker', 'subwoofer', 'power', 'computer', 'microphone']
  const dummy = (kind: Component['kind']) => ({ kind, specs: {} } as unknown as Component)
  return kinds.filter((k) => portsFor(dummy(k), null).some((q) => q.dir === want && (q.signal === p.signal || q.signal === 'other' || p.signal === 'other')))
}
