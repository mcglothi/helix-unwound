import { expect, it } from 'vitest'
import type { SystemView } from '../types'
import { predictionSummary } from '../prediction'

const view = { measurement_count: 2, available_measurement_count: 5, aggregation: 'power_sum',
  coverage: { outputs: ['A', 'B'], missing_outputs: ['C'] } } as SystemView
it('labels the approximation and uncovered active outputs', () => {
  expect(predictionSummary(view)).toBe('Power-sum estimate · outputs A, B · missing C')
})
it('does not suggest missing measurements when captures need review', () => {
  expect(predictionSummary({ ...view, measurement_count: 0 })).toBe('No eligible captures · 5 available for review')
})
it('distinguishes a single measured capture from a sum', () => {
  expect(predictionSummary({ ...view, measurement_count: 1, aggregation: 'single_capture',
    coverage: { outputs: ['A'], missing_outputs: [] } })).toBe('Magnitude estimate · outputs A')
})
