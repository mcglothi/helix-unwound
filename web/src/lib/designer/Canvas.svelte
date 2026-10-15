<script lang="ts">
  import { SvelteFlow, Background, BackgroundVariant, Controls, MiniMap, Panel, useSvelteFlow,
           type Node, type Edge, type Connection as FlowConnection } from '@xyflow/svelte'
  import { app } from '../state.svelte'
  import { theme } from '../theme.svelte'
  import type { Component, Kind } from '../types'
  import { KIND_LABEL, ROLE_COLORS, SIGNAL_STYLE } from '../types'
  import { compatibleKinds, handleId, parseHandle, portsFor, type Port } from '../ports'
  import { autoLayout } from './layout'
  import { drag, mediaUrl } from './drag.svelte'
  import EquipmentNode from './EquipmentNode.svelte'
  import PinNode from './PinNode.svelte'
  import BackdropNode from './BackdropNode.svelte'

  const nodeTypes = { equipment: EquipmentNode, pin: PinNode, backdrop: BackdropNode }
  const flow = useSvelteFlow()

  let view = $state<'flow' | 'cab'>('flow')
  let snap = $state(true)
  let showWires = $state(true)
  let nodes = $state.raw<Node[]>([])
  let edges = $state.raw<Edge[]>([])
  let quick = $state<{ x: number; y: number; flow: { x: number; y: number }; from: { node: string; port: Port }; kinds: Kind[] } | null>(null)
  let backdrop = $state<{ src: string; w: number; h: number } | null>(null)
  let fitPending = false // re-fit once the canvas has redrawn with new positions

  const design = $derived(app.design)
  const colorFor = (c: Component) => {
    const ch = c.channels[0] && app.tune?.channels.find((x) => x.id === c.channels[0])
    if (ch) return ROLE_COLORS[ch.role]
    return c.kind === 'dsp' ? 'var(--accent)' : c.kind === 'power' ? 'var(--warn)' : c.kind === 'amplifier' ? 'var(--c-full)' : c.kind === 'interface' || c.kind === 'controller' ? 'var(--muted)' : 'var(--line-2)'
  }
  const portsOf = (id: string) => {
    const c = design?.components.find((x) => x.id === id)
    return c ? portsFor(c, app.tune) : []
  }
  const findPort = (id: string, h: string | null | undefined) => portsOf(id).find((p) => handleId(p) === h)
  const est = (c: Component) => {
    const ps = portsFor(c, app.tune)
    const main = ps.filter((p) => p.group === 'main')
    const rows = Math.max(main.filter((p) => p.dir === 'in').length, main.filter((p) => p.dir === 'out').length)
    return { w: 250, h: 64 + rows * 24 + (ps.some((p) => p.group === 'power') ? 34 : 8) }
  }

  // cab photo dimensions for the vehicle view
  $effect(() => {
    const src = mediaUrl(design?.vehicle.layout_image)
    if (!src) { backdrop = null; return }
    const im = new Image()
    im.onload = () => { const s = 1100 / im.naturalWidth; backdrop = { src, w: 1100, h: Math.round(im.naturalHeight * s) } }
    im.src = src
  })

  // rebuild the canvas whenever the design (or view) changes
  $effect(() => {
    if (!design) return
    const comps = design.components.filter((c) => view === 'cab' || c.kind !== 'enclosure' || !design.components.some((d) => d.enclosure === c.id))
    const missing = comps.filter((c) => !(view === 'flow' ? c.flow_pos : c.cab_pos))
    let auto: Record<string, { x: number; y: number }> = {}
    if (view === 'flow' && missing.length) {
      auto = autoLayout(comps.map((c) => ({ id: c.id, ...est(c) })), design.connections.map((e) => ({ source: e.src, target: e.dst })))
    }
    const ns: Node[] = []
    if (view === 'cab' && backdrop) {
      ns.push({ id: '__backdrop', type: 'backdrop', position: { x: 0, y: 0 }, data: backdrop, draggable: false, selectable: false, zIndex: -1 })
    }
    comps.forEach((c, i) => {
      const pos = (view === 'flow' ? c.flow_pos : c.cab_pos) ?? auto[c.id] ?? { x: 40 + (i % 8) * 120, y: (backdrop?.h ?? 400) + 40 + Math.floor(i / 8) * 110 }
      ns.push(view === 'flow'
        ? { id: c.id, type: 'equipment', position: pos, data: { c, ports: portsFor(c, app.tune), color: colorFor(c) }, selected: app.selectedComponent === c.id }
        : { id: c.id, type: 'pin', position: pos, data: { c, color: colorFor(c) }, selected: app.selectedComponent === c.id })
    })
    nodes = ns
    // wires saved without port ids attach to the first port of the matching signal type
    const pick = (node: string, port: string, dir: 'in' | 'out', sig: string) => {
      const exact = findPort(node, `${dir}:${port}`)
      const p = exact ?? portsOf(node).find((q) => q.dir === dir && q.signal === sig) ?? portsOf(node).find((q) => q.dir === dir)
      return p ? handleId(p) : undefined
    }
    edges = (view === 'cab' && !showWires) ? [] : design.connections.map((cn) => ({
      id: cn.id, source: cn.src, target: cn.dst,
      sourceHandle: view === 'flow' ? pick(cn.src, cn.src_port, 'out', cn.signal) : 'c',
      targetHandle: view === 'flow' ? pick(cn.dst, cn.dst_port, 'in', cn.signal) : 'c',
      type: view === 'flow' ? 'default' : 'straight',
      style: `stroke:${SIGNAL_STYLE[cn.signal].color}; stroke-width:${view === 'flow' ? 2.5 : 2}; ${SIGNAL_STYLE[cn.signal].dash ? `stroke-dasharray:${SIGNAL_STYLE[cn.signal].dash};` : ''} opacity:${cn.notes.includes('not recorded') ? 0.5 : 0.95}`,
      label: cn.cable || undefined,
      data: { cn },
    }))
    if (fitPending) {
      fitPending = false
      setTimeout(() => flow.fitView({ padding: 0.12, duration: 300 }), 60)
    }
  })

  // ---- connecting -------------------------------------------------------------------------
  function isValidConnection(c: FlowConnection | Edge) {
    if (view !== 'flow' || c.source === c.target) return false
    const a = findPort(c.source, c.sourceHandle), b = findPort(c.target, c.targetHandle)
    if (!a || !b || a.dir !== 'out' || b.dir !== 'in') return false
    return a.signal === b.signal || a.signal === 'other' || b.signal === 'other'
  }
  async function connect(c: FlowConnection, replacing?: string) {
    const a = findPort(c.source, c.sourceHandle), b = findPort(c.target, c.targetHandle)
    if (!a || !b || !design) return
    // plugging into an occupied single input replaces the old wire (Blender's convention)
    const occupied = design.connections.filter((x) => x.dst === c.target && x.dst_port === b.id && x.id !== replacing)
    if (!b.multi) for (const o of occupied) await app.deleteConnection(o.id)
    if (replacing) await app.deleteConnection(replacing)
    await app.addConnection({ src: c.source, src_port: a.id, dst: c.target, dst_port: b.id, signal: a.signal === 'other' ? b.signal : a.signal })
  }
  function onconnectstart(_e: MouseEvent | TouchEvent, p: { nodeId: string | null; handleId: string | null }) {
    const port = p.nodeId ? findPort(p.nodeId, p.handleId) : undefined
    drag.signal = port?.signal ?? null
    drag.fromDir = port?.dir ?? null
    drag.fromNode = p.nodeId
  }
  function onconnectend(e: MouseEvent | TouchEvent, st: any) {
    const from = drag.fromNode
    drag.signal = null; drag.fromDir = null; drag.fromNode = null
    if (view !== 'flow' || st?.isValid || st?.toNode || !from || !st?.fromHandle) return
    const port = findPort(from, st.fromHandle.id)
    if (!port) return
    const pt = 'changedTouches' in e ? e.changedTouches[0] : e
    quick = { x: pt.clientX, y: pt.clientY, flow: flow.screenToFlowPosition({ x: pt.clientX, y: pt.clientY }),
              from: { node: from, port }, kinds: compatibleKinds(port) }
  }
  async function quickAdd(kind: Kind) {
    if (!quick) return
    const q = quick
    quick = null
    const made = await app.addComponent({ kind, name: `New ${KIND_LABEL[kind].toLowerCase()}`,
      flow_pos: { x: Math.round(q.flow.x - (q.from.port.dir === 'out' ? 0 : 250)), y: Math.round(q.flow.y - 30) } } as any)
    if (!made) return
    const theirs = portsFor(made, app.tune).find((p) => p.dir !== q.from.port.dir && (p.signal === q.from.port.signal || p.signal === 'other'))
    if (!theirs) return
    const out = q.from.port.dir === 'out'
    await connect({ source: out ? q.from.node : made.id, sourceHandle: out ? handleId(q.from.port) : handleId(theirs),
                    target: out ? made.id : q.from.node, targetHandle: out ? handleId(theirs) : handleId(q.from.port) } as FlowConnection)
  }

  // ---- moving / deleting / selecting -----------------------------------------------------
  function onnodedragstop({ nodes: moved }: { nodes: Node[] }) {
    const pos: Record<string, { x: number; y: number }> = {}
    for (const n of moved) if (n.id !== '__backdrop') pos[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y) }
    if (Object.keys(pos).length) app.savePositions(view, pos)
  }
  async function onbeforedelete({ nodes: ns, edges: es }: { nodes: Node[]; edges: Edge[] }) {
    const real = ns.filter((n) => n.id !== '__backdrop')
    if (real.length && !confirm(`Remove ${real.length} component${real.length > 1 ? 's' : ''} and their wiring?`)) return false
    for (const e of es) await app.deleteConnection(e.id)
    for (const n of real) await app.deleteComponent(n.id)
    return false // the engine is the source of truth; the canvas rebuilds from it
  }
  async function arrange() {
    if (!design) return
    const comps = design.components.filter((c) => c.kind !== 'enclosure' || !design.components.some((d) => d.enclosure === c.id))
    const pos = autoLayout(comps.map((c) => ({ id: c.id, ...est(c) })), design.connections.map((e) => ({ source: e.src, target: e.dst })))
    fitPending = true
    await app.savePositions('flow', pos)
  }

  // ---- palette drop & cab photo -----------------------------------------------------------
  function ondragover(e: DragEvent) { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy' }
  async function ondrop(e: DragEvent) {
    e.preventDefault()
    const kind = e.dataTransfer?.getData('application/x-helixtune-kind') as Kind
    if (!kind) return
    const p = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    await app.addComponent({ kind, name: `New ${KIND_LABEL[kind].toLowerCase()}`, [view === 'flow' ? 'flow_pos' : 'cab_pos']: { x: Math.round(p.x - 40), y: Math.round(p.y - 20) } } as any)
  }
  let cabInput = $state<HTMLInputElement>()
  async function setCabPhoto(e: Event) {
    const f = (e.currentTarget as HTMLInputElement).files?.[0]
    if (!f || !design) return
    const m = await app.uploadMedia(f, 'vehicle layout')
    if (m) await app.setVehicle({ ...design.vehicle, layout_image: m.id, media: [...design.vehicle.media, m.id] })
  }
  const PALETTE: Kind[] = ['source', 'interface', 'dsp', 'controller', 'amplifier', 'speaker', 'subwoofer', 'enclosure', 'power', 'computer', 'microphone']
  const colorMode = $derived(theme.find(theme.name).variant)
</script>

<div class="canvas" role="application" aria-label="System designer" {ondragover} {ondrop}>
  <SvelteFlow bind:nodes bind:edges {nodeTypes} {isValidConnection} {colorMode}
              fitView minZoom={0.15} maxZoom={2.5} snapGrid={snap ? [10, 10] : undefined}
              selectionOnDrag={false} panOnDrag={[0, 1, 2]} deleteKey={['Delete', 'Backspace']}
              connectionRadius={28}
              onconnect={(c) => connect(c)} {onconnectstart} {onconnectend}
              {onnodedragstop} {onbeforedelete}
              onnodeclick={({ node }) => node.id !== '__backdrop' && (app.selectedComponent = node.id)}
              onpaneclick={() => { app.selectedComponent = null; quick = null }}>
    <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
    <Controls showLock={false} />
    <MiniMap pannable zoomable nodeStrokeWidth={2} width={150} height={100} />
    <Panel position="top-left">
      <div class="bar">
        <div class="seg" role="group" aria-label="View">
          <button class:active={view === 'flow'} aria-pressed={view === 'flow'} onclick={() => { fitPending = true; view = 'flow' }}>Signal flow</button>
          <button class:active={view === 'cab'} aria-pressed={view === 'cab'} onclick={() => { fitPending = true; view = 'cab' }}>Vehicle</button>
        </div>
        {#if view === 'flow'}
          <button onclick={arrange} title="Lay everything out in signal order">Auto-arrange</button>
          <button class:on={snap} aria-pressed={snap} onclick={() => (snap = !snap)}>Snap</button>
        {:else}
          <button class:on={showWires} aria-pressed={showWires} onclick={() => (showWires = !showWires)}>Wires</button>
          <button onclick={() => cabInput?.click()}>{backdrop ? 'Change cab photo' : 'Add cab photo'}</button>
          <input bind:this={cabInput} type="file" accept="image/*" hidden onchange={setCabPhoto} />
        {/if}
        <button onclick={() => flow.fitView({ padding: 0.12, duration: 300 })}>Fit</button>
      </div>
    </Panel>
    <Panel position="bottom-center">
      <div class="palette" aria-label="Drag a component onto the canvas">
        <span class="plabel">Add</span>
        {#each PALETTE as k}
          <button draggable="true" title="Drag onto the canvas, or click to add"
                  ondragstart={(e) => e.dataTransfer?.setData('application/x-helixtune-kind', k)}
                  onclick={() => { const p = flow.screenToFlowPosition({ x: innerWidth / 2, y: innerHeight / 2 }); app.addComponent({ kind: k, name: `New ${KIND_LABEL[k].toLowerCase()}`, [view === 'flow' ? 'flow_pos' : 'cab_pos']: { x: Math.round(p.x), y: Math.round(p.y) } } as any) }}>
            {KIND_LABEL[k]}
          </button>
        {/each}
      </div>
    </Panel>
    {#if view === 'cab' && !backdrop}
      <Panel position="top-center"><div class="hint">Add a photo or top-down image of the cab, then drag each component to where it sits.</div></Panel>
    {/if}
  </SvelteFlow>

  {#if quick}
    <div class="quick panel" style="left:{quick.x}px; top:{quick.y}px" role="menu" aria-label="Add a connected component">
      <div class="qh">Connect {quick.from.port.label} to a new…</div>
      {#each quick.kinds as k}<button role="menuitem" onclick={() => quickAdd(k)}>{KIND_LABEL[k]}</button>{/each}
      <button class="ghost" onclick={() => (quick = null)}>Cancel</button>
    </div>
  {/if}
</div>

<style>
  .canvas { position: relative; width: 100%; height: 100%; min-height: 520px; }
  .bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .bar button { min-height: 32px; font-size: 13px; }
  .seg { display: flex; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
  .seg button { border: 0; background: transparent; color: var(--muted); min-height: 28px; }
  .seg button.active { background: var(--panel-2); color: var(--ink); }
  .palette { display: flex; gap: 4px; align-items: center; max-width: min(560px, 60vw); overflow-x: auto; background: var(--panel);
             border: 1px solid var(--line); border-radius: 10px; padding: 4px; box-shadow: 0 4px 16px rgb(0 0 0 / .3); scrollbar-width: thin; }
  .palette .plabel { font-size: 11px; color: var(--muted); padding: 0 6px; white-space: nowrap; }
  .palette button { min-height: 28px; padding: 0 9px; font-size: 12px; cursor: grab; white-space: nowrap; flex: none; }
  .hint { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; color: var(--muted); font-size: 13px; }
  .quick { position: fixed; z-index: 30; padding: 8px; display: flex; flex-direction: column; gap: 4px; min-width: 200px; transform: translate(8px, 8px); box-shadow: 0 8px 24px rgb(0 0 0 / .4); }
  .qh { font-size: 12px; color: var(--muted); padding: 2px 4px 6px; }
  .quick button { text-align: left; min-height: 32px; }

  /* Svelte Flow chrome follows the app theme */
  .canvas :global(.svelte-flow) {
    --xy-background-color: var(--bg); --xy-background-pattern-color: var(--line-2);
    --xy-edge-stroke: var(--muted); --xy-edge-stroke-selected: var(--accent); --xy-connectionline-stroke: var(--accent);
    --xy-minimap-background-color: var(--panel); --xy-minimap-mask-background-color: color-mix(in srgb, var(--bg) 70%, transparent);
    --xy-minimap-node-background-color: var(--panel-2); --xy-minimap-node-stroke-color: var(--line-2);
    --xy-controls-button-background-color: var(--panel); --xy-controls-button-background-color-hover: var(--panel-2);
    --xy-controls-button-color: var(--ink); --xy-controls-button-border-color: var(--line);
    --xy-node-background-color: transparent; --xy-node-border: none; --xy-node-boxshadow-selected: none;
    --xy-edge-label-background-color: var(--panel); --xy-edge-label-color: var(--muted);
    --xy-selection-background-color: color-mix(in srgb, var(--accent) 12%, transparent); --xy-selection-border: 1px dashed var(--accent);
  }
  .canvas :global(.svelte-flow__node-equipment), .canvas :global(.svelte-flow__node-pin), .canvas :global(.svelte-flow__node-backdrop) { padding: 0; border: 0; background: transparent; width: auto; }
  .canvas :global(.svelte-flow__edge.selected .svelte-flow__edge-path) { stroke-width: 4 !important; }
</style>
