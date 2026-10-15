// Auto-arrange: layered left-to-right layout in signal order (dagre).
import dagre from '@dagrejs/dagre'

export interface Box { id: string; w: number; h: number }

export function autoLayout(boxes: Box[], edges: { source: string; target: string }[]): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', ranksep: 150, nodesep: 36, marginx: 20, marginy: 20 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const b of boxes) g.setNode(b.id, { width: b.w, height: b.h })
  for (const e of edges) if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target)
  dagre.layout(g)
  const out: Record<string, { x: number; y: number }> = {}
  for (const b of boxes) {
    const n = g.node(b.id)
    out[b.id] = { x: Math.round(n.x - b.w / 2), y: Math.round(n.y - b.h / 2) }
  }
  return out
}
