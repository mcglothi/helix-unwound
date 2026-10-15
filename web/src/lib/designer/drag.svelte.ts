// Shared canvas interaction state (which wire type is being dragged right now).
import type { Dir } from '../ports'
import type { Signal } from '../types'

class DragState {
  signal = $state<Signal | null>(null)
  fromDir = $state<Dir | null>(null)
  fromNode = $state<string | null>(null)
}
export const drag = new DragState()

export function mediaUrl(ref: string | null | undefined): string | null {
  if (!ref) return null
  return /^(https?:)?\/\//.test(ref) || ref.startsWith('/') ? ref : `/api/media/${ref}`
}
