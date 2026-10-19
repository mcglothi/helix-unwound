import { expect, it } from 'vitest'
import { canOverwrite, type OverwriteReview } from '../device'
import type { Status } from '../types'
const status = { revision: 5, connection_epoch: 1, device: { kind: 'emulator', writes_enabled: true, sync_state: 'unsynchronized' } } as Status
const review = { revision: 5, connection_epoch: 1, context: 'review', problems: [] } as unknown as OverwriteReview
it('requires deliberate confirmation and a current write connection', () => {
  expect(canOverwrite(review, status, 'OVERWRITE')).toBe(true)
  expect(canOverwrite(review, status, 'overwrite')).toBe(false)
  expect(canOverwrite(review, {...status, device: {...status.device, writes_enabled: false}}, 'OVERWRITE')).toBe(false)
  expect(canOverwrite(null, status, 'OVERWRITE')).toBe(false)
})
it('refuses stale reviews and reported safety problems', () => {
  expect(canOverwrite(review, {...status, revision: 6}, 'OVERWRITE')).toBe(false)
  expect(canOverwrite(review, {...status, connection_epoch: 2}, 'OVERWRITE')).toBe(false)
  expect(canOverwrite({...review, problems: ['Missing high-pass']}, status, 'OVERWRITE')).toBe(false)
})
it('allows deliberate recovery from uncertainty but refuses in-flight writes', () => {
  expect(canOverwrite(review, {...status, device: {...status.device, sync_state:'uncertain'}}, 'OVERWRITE')).toBe(true)
  expect(canOverwrite(review, {...status, device: {...status.device, sync_state:'applying'}}, 'OVERWRITE')).toBe(false)
})
it('refuses a physical overwrite with unverified settings or after a missed keep-alive', () => {
  expect(canOverwrite({...review, physical: true, ineligible: ['A HP bessel 24 dB/oct is not verified']}, status, 'OVERWRITE')).toBe(false)
  expect(canOverwrite({...review, physical: true, ineligible: [], excluded: ['master gain']}, status, 'OVERWRITE')).toBe(true)
  expect(canOverwrite(review, {...status, device: {...status.device, needs_reconnect: true}}, 'OVERWRITE')).toBe(false)
})
