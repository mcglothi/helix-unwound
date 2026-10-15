import { describe, it, expect } from 'vitest'
import type { ProtectionConstraint } from './types'
import { canReviewConstraint, constraintLabel } from './protections'
const item: ProtectionConstraint = {
  id: 'example', output: 'A', field: 'min_hp_hz', value: 2600, unit: 'Hz',
  source: {}, current: true, state: 'pending', fingerprint: 'revision', history: [],
}
describe('individual constraint review', () => {
  it('requires evidence and a current pending source to confirm', () => {
    expect(canReviewConstraint(item, false, ' ').confirm).toBe(false)
    expect(canReviewConstraint(item, true, 'datasheet and wiring checked').confirm).toBe(true)
    expect(canReviewConstraint({ ...item, current: false }, false, 'checked').confirm).toBe(false)
    expect(canReviewConstraint({ ...item, state: 'confirmed' }, false, 'checked').confirm).toBe(false)
  })
  it('allows clearing only orphaned enforced constraints while disconnected', () => {
    expect(canReviewConstraint(item, false, 'old driver removed').clear).toBe(false)
    const orphan = { ...item, current: false }
    expect(canReviewConstraint(orphan, true, 'removed').clear).toBe(false)
    expect(canReviewConstraint(orphan, false, '').clear).toBe(false)
    expect(canReviewConstraint(orphan, false, 'removed').clear).toBe(true)
    expect(canReviewConstraint({ ...orphan, state: 'cleared' }, false, 'removed').clear).toBe(false)
  })
  it('labels the exact enforced value and unit', () => {
    expect(constraintLabel(item)).toBe('HP ≥ 2600 Hz')
    expect(constraintLabel({ ...item, field: 'max_lp_hz', value: 10000 })).toBe('LP ≤ 10000 Hz')
  })
})
