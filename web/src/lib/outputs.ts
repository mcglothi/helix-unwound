import type { Channel, Role, Source } from './types'
import { ROLE_LABEL, SOURCE_LABEL, SOURCE_MIX, sourceOf } from './types'

export interface OutputSetupReview { channel: Channel; context: string; live: boolean }
export interface OutputDraft { name: string; role: Role; source: Source }
export function setupMix(source: Source, original: Record<string, number>): Record<string, number> {
  return { ...(source === 'custom' ? original : SOURCE_MIX[source]) }
}
export function routeLabel(mix: Record<string, number>): string {
  return sourceOf(mix) === 'custom'
    ? `Custom · L × ${mix.L ?? 0}, R × ${mix.R ?? 0}` : SOURCE_LABEL[sourceOf(mix)]
}
export function setupChanges(channel: Pick<Channel, 'name' | 'role' | 'mix'>, draft: OutputDraft): { label: string; before: string; after: string }[] {
  const changes = []
  if (channel.name !== draft.name) changes.push({ label: 'Name', before: channel.name || 'Unnamed', after: draft.name || 'Unnamed' })
  if (channel.role !== draft.role) changes.push({ label: 'Role', before: ROLE_LABEL[channel.role], after: ROLE_LABEL[draft.role] })
  const mix = setupMix(draft.source, channel.mix)
  if ((channel.mix.L ?? 0) !== (mix.L ?? 0) || (channel.mix.R ?? 0) !== (mix.R ?? 0))
    changes.push({ label: 'Input route', before: routeLabel(channel.mix), after: routeLabel(mix) })
  return changes
}
