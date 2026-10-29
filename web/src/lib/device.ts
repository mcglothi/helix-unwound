export { workstationRequest as deviceRequest } from './http'
import type { Device, Status } from './types'
export interface Port { device: string; description: string }
export interface OverwriteReview {
  context: string; revision: number; connection_epoch: number; tune_name: string
  device: Device; problems: string[]; parameter_count: number
  /** real DSP: settings not capture-verified (refused) and parameters left out of the write */
  physical?: boolean; ineligible?: string[]; excluded?: string[]
}
export function canOverwrite(review: OverwriteReview | null, status: Status | null, confirmation: string): boolean {
  return !!review && !!status && confirmation === 'OVERWRITE' && !review.problems.length &&
    !review.ineligible?.length && !status.device.needs_reconnect &&
    review.revision === status.revision && review.connection_epoch === status.connection_epoch &&
    status.device.kind !== 'none' && status.device.writes_enabled &&
    ['unsynchronized', 'uncertain', 'synchronized'].includes(status.device.sync_state)
}

export function connectionStatus(status: Status | null): string {
  if (!status || status.device.kind === 'none') return 'Offline editing'
  if (status.device.sync_state === 'uncertain') return 'Recovery needed'
  if (!status.device.writes_enabled) return 'Read-only connection'
  if (status.device.sync_state === 'applying') return 'Sending settings…'
  return status.device.baselined ? 'Writes active' : 'Ready for review'
}
