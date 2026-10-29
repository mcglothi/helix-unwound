import type { SystemView } from './types'

export function predictionSummary(system: SystemView | null): string {
  if (!system) return 'Loading response context…'
  if (!system.measurement_count) return `No eligible captures · ${system.available_measurement_count} available for review`
  const method = system.aggregation === 'power_sum' ? 'Power-sum estimate' : 'Magnitude estimate'
  const missing = system.coverage.missing_outputs
  return `${method} · outputs ${system.coverage.outputs.join(', ')}${missing.length ? ` · missing ${missing.join(', ')}` : ''}`
}
