export type Shortcut = 'undo' | 'redo' | 'previous-output' | 'next-output' | 'help'
interface Keys { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean; repeat: boolean }
export function shortcutFor(event: Keys, editable: boolean, modalOpen: boolean): Shortcut | null {
  if (editable || modalOpen || event.repeat || event.altKey) return null
  const key = event.key.toLowerCase()
  if (event.ctrlKey || event.metaKey) {
    if (key === 'z') return event.shiftKey ? 'redo' : 'undo'
    if (key === 'y' && event.ctrlKey && !event.metaKey && !event.shiftKey) return 'redo'
    return null
  }
  if (event.key === '?') return 'help'
  if (!event.shiftKey && key === '[') return 'previous-output'
  if (!event.shiftKey && key === ']') return 'next-output'
  return null
}
export function adjacentOutput(ids: string[], current: string, direction: -1 | 1): string {
  if (!ids.length) return current
  const index = ids.indexOf(current)
  return ids[(Math.max(0, index) + direction + ids.length) % ids.length]
}
