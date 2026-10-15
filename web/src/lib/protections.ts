import type { ProtectionConstraint } from './types'

export function constraintLabel(item: ProtectionConstraint): string {
  const labels = { min_hp_hz: 'HP ≥', min_hp_slope_db: 'HP slope ≥', max_lp_hz: 'LP ≤', fs_factor: 'Fs multiplier ≥' }
  return `${labels[item.field]} ${item.value} ${item.unit}`
}

export function canReviewConstraint(item: ProtectionConstraint, connected: boolean, reason: string) {
  const evidence = !!reason.trim() && reason.length <= 2000
  return {
    confirm: evidence && item.current && item.state === 'pending',
    clear: evidence && !item.current && item.state !== 'cleared' && !connected,
  }
}
