<script lang="ts">
  import { app } from '../state.svelte'
  import { eqCurve, fmtDb, fmtHz, logFreqs } from '../dsp'
  import type { EqBand } from '../types'
  import { ROLE_COLORS } from '../types'

  let { compact = false }: { compact?: boolean } = $props()

  let w = $state(800)
  let h = $state(380)
  const F_LO = 20, F_HI = 20000
  const EQ_RANGE = 15 // ± dB on the EQ overlay axis
  const pad = { l: 40, r: 40, t: 10, b: 22 }

  const x = (f: number) => pad.l + ((Math.log10(f / F_LO)) / Math.log10(F_HI / F_LO)) * (w - pad.l - pad.r)
  const fAt = (px: number) => F_LO * (F_HI / F_LO) ** ((px - pad.l) / (w - pad.l - pad.r))

  const sys = $derived(app.system)
  const hasMeas = $derived(!!sys?.predicted)

  // acoustic y-range from visible data
  const yRange = $derived.by(() => {
    if (!sys?.predicted) return [-40, 15]
    const vals = [...(sys.predicted ?? []), ...(sys.target ?? []), ...(app.layers.measured ? sys.measured ?? [] : [])]
    const lo = Math.min(...vals), hi = Math.max(...vals)
    return [Math.floor((lo - 4) / 5) * 5, Math.ceil((hi + 4) / 5) * 5]
  })
  const y = (db: number) => pad.t + ((yRange[1] - db) / (yRange[1] - yRange[0])) * (h - pad.t - pad.b)
  const yEq = (db: number) => pad.t + ((EQ_RANGE - db) / (2 * EQ_RANGE)) * (h - pad.t - pad.b)
  const gAtEq = (py: number) => EQ_RANGE - ((py - pad.t) / (h - pad.t - pad.b)) * 2 * EQ_RANGE

  function path(freqs: number[], vals: number[] | null | undefined, yf = y) {
    if (!vals) return ''
    let d = ''
    for (let i = 0; i < freqs.length; i++) {
      const f = freqs[i]
      if (f < F_LO || f > F_HI) continue
      const yy = Math.max(pad.t, Math.min(h - pad.b, yf(vals[i])))
      d += `${d ? 'L' : 'M'}${x(f).toFixed(1)},${yy.toFixed(1)}`
    }
    return d
  }

  // ---- EQ overlay for the selected channel, with local drag state for instant feedback ----
  const ch = $derived(app.channel)
  let draft = $state<EqBand[] | null>(null)
  const bands = $derived(draft ?? ch?.eq ?? [])
  const eqF = logFreqs(240)
  const eqPath = $derived(path(eqF, eqCurve(bands, eqF, app.tune?.sample_rate ?? 96000), yEq))
  const chColor = $derived(ch ? ROLE_COLORS[ch.role] : 'var(--accent)')

  let dragging = $state<number | null>(null)
  let lastSent = 0
  let sendTimer: ReturnType<typeof setTimeout> | undefined

  function send(i: number) {
    if (!ch || !draft) return
    const b = draft[i]
    app.patchBand(ch.id, i + 1, { freq_hz: Math.round(b.freq_hz), gain_db: Math.round(b.gain_db * 4) / 4, q: b.q, enabled: true })
  }

  function pointerPos(e: PointerEvent | WheelEvent | MouseEvent) {
    const r = (e.currentTarget as SVGElement).closest('svg')!.getBoundingClientRect()
    return [e.clientX - r.left, e.clientY - r.top]
  }

  function down(e: PointerEvent, i: number) {
    if (!ch) return
    e.stopPropagation()
    ;(e.target as Element).setPointerCapture(e.pointerId)
    draft = ch.eq.map((b) => ({ ...b }))
    dragging = i
  }
  function move(e: PointerEvent) {
    const [px, py] = pointerPos(e)
    hover = { px, py }
    if (dragging === null || !draft) return
    const f = Math.min(20000, Math.max(20, fAt(px)))
    const g = Math.max(-EQ_RANGE, Math.min(EQ_RANGE, gAtEq(py)))
    draft[dragging] = { ...draft[dragging], freq_hz: f, gain_db: g }
    const now = performance.now()
    clearTimeout(sendTimer)
    if (now - lastSent > 150) { lastSent = now; send(dragging) } else { sendTimer = setTimeout(() => dragging !== null && send(dragging), 150) }
  }
  async function up() {
    if (dragging !== null) {
      clearTimeout(sendTimer)
      await send(dragging)
    }
    dragging = null
    draft = null
  }
  function wheel(e: WheelEvent, i: number) {
    if (!ch) return
    e.preventDefault()
    const b = ch.eq[i]
    const q = Math.max(0.3, Math.min(20, +(b.q * (e.deltaY < 0 ? 1.12 : 1 / 1.12)).toFixed(2)))
    app.patchBand(ch.id, i + 1, { q })
  }
  function toggle(i: number) {
    if (ch) app.patchBand(ch.id, i + 1, { enabled: !ch.eq[i].enabled })
  }
  function addAt(e: MouseEvent) {
    if (!ch || compact) return
    const free = ch.eq.findIndex((b) => !b.enabled)
    if (free < 0) return app.toast('All 30 bands are in use on this channel')
    const [px, py] = pointerPos(e)
    app.patchBand(ch.id, free + 1, { enabled: true, type: 'peak', freq_hz: Math.round(fAt(px)), gain_db: Math.round(gAtEq(py) * 2) / 2, q: 2 })
  }

  let hover = $state<{ px: number; py: number } | null>(null)
  const readout = $derived.by(() => {
    if (!hover || !sys) return null
    const f = fAt(hover.px)
    if (f < F_LO || f > F_HI) return null
    const at = (vals: number[] | null | undefined) => {
      if (!vals) return null
      let best = 0
      for (let i = 1; i < sys.freqs.length; i++) if (Math.abs(Math.log(sys.freqs[i] / f)) < Math.abs(Math.log(sys.freqs[best] / f))) best = i
      return vals[best]
    }
    return { f, pred: at(sys.predicted), meas: at(sys.measured), tgt: at(sys.target) }
  })

  const gridF = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
  const gridDb = $derived(Array.from({ length: Math.floor((yRange[1] - yRange[0]) / 10) + 1 }, (_, i) => Math.ceil(yRange[0] / 10) * 10 + i * 10).filter((d) => d <= yRange[1]))
</script>

<div class="graph" bind:clientWidth={w} bind:clientHeight={h} class:compact>
  <svg width={w} height={h} role="img" aria-label="Frequency response"
       onpointermove={move} onpointerup={up} onpointerleave={() => (hover = null)} ondblclick={addAt}>
    {#each gridF as f}
      <line x1={x(f)} x2={x(f)} y1={pad.t} y2={h - pad.b} class="grid" />
      <text x={x(f)} y={h - 6} class="tick" text-anchor="middle">{fmtHz(f)}</text>
    {/each}
    {#if hasMeas}
      {#each gridDb as d}
        <line x1={pad.l} x2={w - pad.r} y1={y(d)} y2={y(d)} class="grid" />
        <text x={pad.l - 6} y={y(d) + 3} class="tick" text-anchor="end">{d}</text>
      {/each}
    {/if}
    {#if !compact}
      {#each [-12, -6, 0, 6, 12] as d}
        <text x={w - pad.r + 6} y={yEq(d) + 3} class="tick eqtick">{d > 0 ? '+' : ''}{d}</text>
      {/each}
      <line x1={pad.l} x2={w - pad.r} y1={yEq(0)} y2={yEq(0)} class="zero" />
    {/if}

    {#if sys && hasMeas}
      {#if app.layers.groups}
        {#each Object.entries(sys.groups) as [role, vals]}
          <path d={path(sys.freqs, vals)} class="curve" style="stroke:{ROLE_COLORS[role as keyof typeof ROLE_COLORS]}; opacity:.5; stroke-width:1.5" />
        {/each}
      {/if}
      {#if app.layers.measured}<path d={path(sys.freqs, sys.measured)} class="curve" style="stroke:var(--dim); stroke-width:2" />{/if}
      {#if app.layers.target}<path d={path(sys.freqs, sys.target)} class="curve" style="stroke:var(--ink); stroke-dasharray:7 6; stroke-width:2" />{/if}
      {#if app.layers.predicted}<path d={path(sys.freqs, sys.predicted)} class="curve" style="stroke:var(--accent); stroke-width:3; opacity:{app.preview ? 0.45 : 1}" />{/if}
      {#if app.preview?.predicted}<path d={path(app.preview.freqs, app.preview.predicted)} class="curve" style="stroke:var(--accent); stroke-width:3; stroke-dasharray:9 5" />{/if}
    {/if}

    {#if !compact}
      <path d={eqPath} class="curve" style="stroke:{chColor}; stroke-width:2; opacity:.9" />
      {#each bands as b, i}
        {#if b.enabled}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <g class="node" class:active={dragging === i}
             onpointerdown={(e) => down(e, i)} onwheel={(e) => wheel(e, i)} ondblclick={(e) => { e.stopPropagation(); toggle(i) }}>
            <circle cx={x(b.freq_hz)} cy={yEq(b.gain_db)} r="16" class="hit" />
            <circle cx={x(b.freq_hz)} cy={yEq(b.gain_db)} r="7" style="fill:{chColor}" class="dot" />
            <text x={x(b.freq_hz)} y={yEq(b.gain_db) - 12} text-anchor="middle" class="nlabel">{i + 1}</text>
          </g>
        {/if}
      {/each}
    {/if}

    {#if readout}
      <line x1={hover!.px} x2={hover!.px} y1={pad.t} y2={h - pad.b} class="cursor" />
    {/if}
  </svg>
  {#if !hasMeas}
    <div class="empty">No measurements for this seat yet — showing EQ only. Import from REW or measure.</div>
  {/if}
  {#if readout && hasMeas}
    <div class="readout mono">
      {fmtHz(readout.f)} Hz · pred {readout.pred?.toFixed(1)} · meas {readout.meas?.toFixed(1)} · target {readout.tgt?.toFixed(1)}
      {#if readout.pred != null && readout.tgt != null}<b>({fmtDb(readout.pred - readout.tgt)} dB)</b>{/if}
    </div>
  {/if}
</div>

<style>
  .graph { position: relative; width: 100%; height: 100%; min-height: 220px; user-select: none; touch-action: none; }
  svg { position: absolute; inset: 0; display: block; }
  .grid { stroke: var(--line); stroke-width: 1; }
  .zero { stroke: var(--line-2); stroke-dasharray: 2 4; }
  .tick { fill: var(--dim); font: 11px var(--mono); }
  .eqtick { fill: var(--dim); opacity: .7; }
  .curve { fill: none; stroke-linejoin: round; stroke-linecap: round; }
  .node { cursor: grab; }
  .node.active { cursor: grabbing; }
  .hit { fill: transparent; }
  .dot { stroke: var(--bg); stroke-width: 2; }
  .node:hover .dot, .node.active .dot { stroke: var(--ink); }
  .nlabel { fill: var(--ink); font: 600 10px var(--mono); pointer-events: none; }
  .cursor { stroke: var(--ink); opacity: .3; }
  .readout { position: absolute; top: 8px; right: 48px; font-size: 12px; color: var(--muted); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 3px 8px; pointer-events: none; }
  .readout b { color: var(--ink); font-weight: 500; }
  .empty { position: absolute; left: 50%; top: 40%; transform: translate(-50%, -50%); color: var(--muted); font-size: 14px; text-align: center; max-width: 80%; pointer-events: none; }
</style>
