import type { Proposal } from './types'

/** Apply is allowed only for a proposal with changes and no known conflicts. */
export const canApply = (p: Proposal | null, conflicts: string[]): boolean =>
  !!p && p.edits.length > 0 && conflicts.length === 0
