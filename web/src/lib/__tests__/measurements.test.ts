import { describe, expect, it } from 'vitest'
import { canRecordHardware, captureDraft, sameDrivers, type MeasurementRecord } from '../measurements'

const current = { A: [{ id: 'door-left', make: 'Audiofrog', model: 'GS690' }] }
const record = { id: 'legacy-2018', channels: ['A'], drivers: null, current_drivers: current } as unknown as MeasurementRecord

describe('capture-time hardware review', () => {
  it('does not prefill unknown historical records from installed drivers', () => {
    const draft = captureDraft(record)
    expect(draft.A[0].make).toBe('')
    expect(draft.A[0].model).toBe('')
    expect(draft.A[0].id).toContain('historical:')
    expect(sameDrivers(draft, current)).toBe(false)
  })
  it('preserves recorded historical hardware without mutating it', () => {
    const historical = { ...record, drivers: { A: [{ id: 'old-door', make: 'Audiofrog', model: 'GB60' }] } }
    const draft = captureDraft(historical)
    expect(draft.A[0].model).toBe('GB60')
    draft.A[0].model = 'edited'
    expect(historical.drivers.A[0].model).toBe('GB60')
  })
  it('requires evidence, explicit review, and complete identities', () => {
    expect(canRecordHardware(record, current, 'Capture notes verified', false, false)).toBe(false)
    expect(canRecordHardware(record, current, '   ', true, false)).toBe(false)
    expect(canRecordHardware(record, captureDraft(record), 'Capture notes verified', true, false)).toBe(false)
    expect(canRecordHardware(record, current, 'Capture notes verified', true, false)).toBe(true)
  })
  it('requires an explicit correction before replacing a known historical identity', () => {
    const historical = { ...record, drivers: { A: [{ id: 'old-door', make: 'Audiofrog', model: 'GB60' }] } }
    expect(canRecordHardware(historical, current, 'Capture notes corrected', true, false)).toBe(false)
    expect(canRecordHardware(historical, current, 'Capture notes corrected', true, true)).toBe(true)
  })
  it('rejects empty, extra or duplicate output identities', () => {
    expect(canRecordHardware(record, {}, 'Capture notes verified', true, false)).toBe(false)
    expect(canRecordHardware(record, { A: [], B: current.A }, 'Capture notes verified', true, false)).toBe(false)
    expect(canRecordHardware(record, { A: [...current.A, ...current.A] }, 'Capture notes verified', true, false)).toBe(false)
  })
})
