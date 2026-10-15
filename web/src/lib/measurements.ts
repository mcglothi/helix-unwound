export interface CaptureDriver { id: string; make: string; model: string }
export type CaptureDrivers = Record<string, CaptureDriver[]>
export interface DriverEvent {
  action: 'attest' | 'correct' | 'invalidate'; at: number; source: string; reason: string
  drivers: CaptureDrivers | null; previous_drivers: CaptureDrivers | null
}
export interface MeasurementRecord {
  id: string; name: string; channels: string[]; seat: string; taken_at: number; source: string; notes: string
  kind: string; has_tune: boolean; tune_name: string | null; has_phase: boolean
  drivers: CaptureDrivers | null; current_drivers: CaptureDrivers; driver_history: DriverEvent[]
  status: 'current' | 'unknown' | 'stale'; status_reason: string; optimizable: boolean
  capture_fingerprint: string; drivers_source: string
}

export const hardwareLabel = (status: MeasurementRecord['status']): string =>
  status === 'current' ? 'Matches installed drivers' : status === 'stale' ? 'Different hardware' : 'Capture hardware unknown'

export function captureDraft(measurement: MeasurementRecord): CaptureDrivers {
  return Object.fromEntries(measurement.channels.map((channel) => [channel,
    (measurement.drivers?.[channel]?.length ? measurement.drivers[channel] :
      [{ id: `historical:${measurement.id}:${channel}:0`, make: '', model: '' }]).map((driver) => ({ ...driver })),
  ]))
}

export function sameDrivers(left: CaptureDrivers | null, right: CaptureDrivers): boolean {
  if (left === null) return false
  const canonical = (drivers: CaptureDrivers) => Object.keys(drivers).sort().map((channel) =>
    [channel, drivers[channel].map((d) => ({ id: d.id, make: d.make.trim(), model: d.model.trim() }))
      .sort((a, b) => a.id.localeCompare(b.id))])
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right))
}

export function canRecordHardware(measurement: MeasurementRecord | null, drivers: CaptureDrivers,
  reason: string, reviewed: boolean, correction: boolean): boolean {
  if (!measurement || !measurement.channels.length || !reviewed || reason.trim().length < 8) return false
  if (measurement.drivers !== null && !sameDrivers(measurement.drivers, drivers) && !correction) return false
  if (Object.keys(drivers).sort().join() !== [...measurement.channels].sort().join()) return false
  return measurement.channels.every((channel) => {
    const refs = drivers[channel] ?? []
    return refs.length > 0 && new Set(refs.map((d) => d.id)).size === refs.length &&
      refs.every((d) => d.id && d.make.trim() && d.model.trim())
  })
}
