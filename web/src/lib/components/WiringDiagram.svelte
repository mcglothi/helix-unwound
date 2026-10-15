<script lang="ts">
  import { app } from '../state.svelte'
  import type { Component, Kind } from '../types'
  import { KIND_LABEL, ROLE_COLORS, SIGNAL_STYLE } from '../types'

  // Columns follow the signal: source & power -> DSP & mic -> amplifiers -> drivers.
  const COL: Record<Kind, number> = {
    source: 0, interface: 0, controller: 1, power: 0, computer: 0, other: 0, dsp: 1, microphone: 1, amplifier: 2,
    speaker: 3, subwoofer: 3, enclosure: 3,
  }
  const CW = 220, CH = 66, GX = 90, GY = 18, PAD = 20, HEAD = 30, EMPTY_W = 110

  const design = $derived(app.design)
  const roleOf = (c: Component) => {
    const ch = c.channels[0] && app.tune?.channels.find((x) => x.id === c.channels[0])
    return ch ? ch.role : null
  }
  const layout = $derived.by(() => {
    const pos = new Map<string, { x: number; y: number; c: Component }>()
    if (!design) return { pos, w: 0, h: 0, xs: [] as number[], empty: [] as boolean[] }
    const cols: Component[][] = [[], [], [], []]
    // enclosures are drawn inside their driver's card, so skip ones that are assigned
    const housed = new Set(design.components.map((c) => c.enclosure).filter(Boolean) as string[])
    for (const c of design.components) if (!(c.kind === 'enclosure' && housed.has(c.id))) cols[COL[c.kind]].push(c)
    const order = ['subwoofer', 'midbass', 'woofer', 'midrange', 'tweeter', 'fullrange']
    cols[3].sort((a, b) => order.indexOf(roleOf(a) ?? '') - order.indexOf(roleOf(b) ?? '') || a.name.localeCompare(b.name))
    cols[0].sort((a, b) => (a.kind === 'power' ? 1 : 0) - (b.kind === 'power' ? 1 : 0))
    // empty columns shrink to a narrow labelled gap instead of a full card width
    const xs: number[] = []
    let x = PAD
    cols.forEach((list) => { xs.push(x); x += (list.length ? CW : EMPTY_W) + GX })
    let h = PAD + HEAD + CH + PAD
    cols.forEach((list, i) => list.forEach((c, j) => {
      const y = PAD + HEAD + j * (CH + GY)
      pos.set(c.id, { x: xs[i], y, c })
      h = Math.max(h, y + CH + PAD)
    }))
    return { pos, w: x - GX + PAD, h, xs, empty: cols.map((l) => !l.length) }
  })

  const wires = $derived.by(() => {
    if (!design) return []
    return design.connections.map((cn) => {
      const a = layout.pos.get(cn.src), b = layout.pos.get(cn.dst)
      if (!a || !b) return null
      const back = b.x <= a.x
      const x1 = back ? a.x : a.x + CW, y1 = a.y + CH / 2
      const x2 = back ? b.x + CW : b.x, y2 = b.y + CH / 2
      const dx = Math.max(40, Math.abs(x2 - x1) / 2) * (back ? -1 : 1)
      return { cn, d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`, lx: x2 + (back ? 8 : -8), ly: y2 - 6, back }
    }).filter((w): w is NonNullable<typeof w> => w !== null)
  })
  const sub = (c: Component) => [c.make, c.model].filter(Boolean).join(' ') || 'model not recorded'
  const encName = (c: Component) => c.enclosure ? design?.components.find((x) => x.id === c.enclosure) : null
  const accentFor = (c: Component) => {
    const r = roleOf(c)
    return r ? ROLE_COLORS[r] : c.kind === 'dsp' ? 'var(--accent)' : c.kind === 'power' ? 'var(--warn)' : 'var(--line-2)'
  }
  const COLS = ['Source & power', 'Processing', 'Amplification', 'Drivers']
  const usedSignals = $derived([...new Set(design?.connections.map((c) => c.signal) ?? [])])
</script>

<div class="wrap">
  <div class="legend">
    {#each usedSignals as s}
      <span><svg width="22" height="8" aria-hidden="true"><line x1="0" y1="4" x2="22" y2="4" stroke={SIGNAL_STYLE[s].color} stroke-width="3" stroke-dasharray={SIGNAL_STYLE[s].dash ?? ''} /></svg>{SIGNAL_STYLE[s].label}</span>
    {/each}
  </div>
  <div class="scroll">
    <svg viewBox="0 0 {layout.w} {layout.h}" style="width:100%; min-width:{Math.min(layout.w, 600)}px; max-width:{layout.w}px" role="img" aria-label="System wiring diagram">
      {#each COLS as t, i}
        <text x={layout.xs[i]} y={PAD + 12} class="colhead">{(layout.empty[i] ? t.split(' ')[0] : t).toUpperCase()}</text>
        {#if layout.empty[i]}<text x={layout.xs[i]} y={PAD + HEAD + 20} class="none">none recorded</text>{/if}
      {/each}
      {#each wires as w (w.cn.id)}
        <path d={w.d} fill="none" stroke={SIGNAL_STYLE[w.cn.signal].color} stroke-width="2.5"
              stroke-dasharray={SIGNAL_STYLE[w.cn.signal].dash ?? ''} opacity={w.cn.notes.includes('not recorded') ? 0.45 : 0.9} />
        {#if w.cn.src_port}<text x={w.lx} y={w.ly} class="port" text-anchor={w.back ? 'start' : 'end'}>{w.cn.src_port}</text>{/if}
      {/each}
      {#each [...layout.pos.values()] as p (p.c.id)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <g class="card" class:sel={app.selectedComponent === p.c.id} role="button" tabindex="0"
           aria-label="{KIND_LABEL[p.c.kind]}: {p.c.name || sub(p.c)}"
           onclick={() => (app.selectedComponent = p.c.id)}
           onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && (app.selectedComponent = p.c.id)}>
          <rect x={p.x} y={p.y} width={CW} height={CH} rx="8" class="box" />
          <rect x={p.x} y={p.y} width="4" height={CH} rx="2" fill={accentFor(p.c)} />
          <text x={p.x + 14} y={p.y + 20} class="kind">{KIND_LABEL[p.c.kind].toUpperCase()}{p.c.channels.length ? ` · ${p.c.channels.join(',')}` : ''}</text>
          <text x={p.x + 14} y={p.y + 38} class="name">{(p.c.name || sub(p.c)).slice(0, 24)}</text>
          <text x={p.x + 14} y={p.y + 55} class="sub" class:missing={!p.c.model}>{(encName(p.c) ? `${sub(p.c)} · in ${encName(p.c)!.name || 'enclosure'}` : sub(p.c)).slice(0, 27)}</text>
        </g>
      {/each}
    </svg>
  </div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--muted); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .scroll { overflow: auto; max-width: 100%; }
  svg { display: block; }
  .colhead { fill: var(--muted); font: 600 11px var(--font); letter-spacing: .1em; }
  .box { fill: var(--panel-2); stroke: var(--line-2); }
  .card { cursor: pointer; outline: none; }
  .card:hover .box, .card:focus-visible .box { stroke: var(--muted); }
  .card.sel .box { stroke: var(--accent); stroke-width: 2; }
  .kind { fill: var(--muted); font: 600 10px var(--font); letter-spacing: .08em; }
  .name { fill: var(--ink); font: 600 14px var(--font); }
  .sub { fill: var(--muted); font: 12px var(--mono); }
  .sub.missing { fill: var(--dim); font-style: italic; }
  .port { fill: var(--muted); font: 11px var(--mono); }
  .none { fill: var(--dim); font: italic 12px var(--font); }
</style>
