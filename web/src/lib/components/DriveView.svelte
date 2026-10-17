<script lang="ts">
  import { app } from '../state.svelte'
  import Graph from './Graph.svelte'
  import PredictionSummary from './PredictionSummary.svelte'
  import ProposalCard from './ProposalCard.svelte'
  import type { Role } from '../types'
  import { ROLE_COLORS, ROLE_LABEL } from '../types'

  // Drive mode: the same look as Studio, scaled up for use in the car (see --tap in theme.css).
  const GROUPS: Role[] = ['subwoofer', 'midbass', 'midrange', 'tweeter']
  const groups = $derived(
    GROUPS.map((r) => ({ r, chans: (app.tune?.channels ?? []).filter((c) => c.role === r) })).filter((g) => g.chans.length),
  )
  const avg = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
  const fmt = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(1)}`

  async function nudge(role: Role, d: number) {
    for (const c of (app.tune?.channels ?? []).filter((c) => c.role === role)) {
      await app.patchChannel(c.id, { gain_db: Math.round((c.gain_db + d) * 2) / 2 }, { link: false })
    }
  }
  const master = $derived(app.tune?.master_gain_db ?? 0)
  const ab = $derived(app.status?.ab)
  const SEATS = [{ v: 'driver', l: 'Driver' }, { v: 'passenger', l: 'Passenger' }, { v: 'center', l: 'Both seats' }]
</script>

<div class="drive">
  <div class="seg" role="group" aria-label="Listening seat">
    {#each SEATS as s}
      <button class:active={app.seat === s.v} aria-pressed={app.seat === s.v} onclick={() => app.setSeat(s.v)}>{s.l}</button>
    {/each}
  </div>

  <section class="panel graph">
    <div class="head"><span class="label">Response · {app.seat}</span><span class="mono muted">target: {app.system?.target_name ?? '—'}</span></div>
    <PredictionSummary />
    <div class="plot"><Graph compact /></div>
  </section>

  <ProposalCard />

  <section class="levels">
    {#each groups as g}
      <div class="panel tile">
        <div class="head"><span class="swatch" style="background:{ROLE_COLORS[g.r]}"></span><span class="label">{ROLE_LABEL[g.r]}</span></div>
        <div class="val mono">{fmt(avg(g.chans.map((c) => c.gain_db)))}<small> dB</small></div>
        <div class="pm">
          <button aria-label="{ROLE_LABEL[g.r]} down 1 dB" onclick={() => nudge(g.r, -1)}>−</button>
          <button aria-label="{ROLE_LABEL[g.r]} up 1 dB" onclick={() => nudge(g.r, 1)}>+</button>
        </div>
      </div>
    {/each}
    <div class="panel tile">
      <div class="head"><span class="swatch" style="background:var(--accent)"></span><span class="label">Master</span></div>
      <div class="val mono">{fmt(master)}<small> dB</small></div>
      <div class="pm">
        <button aria-label="Master down 1 dB" onclick={() => app.setMaster(Math.max(-80, master - 1))}>−</button>
        <button aria-label="Master up 1 dB" onclick={() => app.setMaster(Math.min(0, master + 1))}>+</button>
      </div>
    </div>
  </section>

  <div class="actions">
    <button class="primary" onclick={() => app.toast('Live measurement arrives with the REW link and the in-truck mic', 'info')}>Measure this seat</button>
    <button disabled={!(ab?.A && ab?.B)} onclick={() => app.toggleAB()}>
      A / B{#if ab?.active} · on {ab.active}{/if}
    </button>
    <button disabled={!app.status?.undo_depth} onclick={() => app.undo()}>Undo</button>
  </div>
</div>

<style>
  .drive { display: flex; flex-direction: column; gap: var(--gap); padding: var(--gap); max-width: 1200px; margin: 0 auto; }
  .seg { display: flex; background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius); padding: 4px; }
  .seg button { flex: 1; border: 0; background: transparent; color: var(--muted); }
  .seg button.active { background: var(--panel-2); color: var(--ink); font-weight: 600; box-shadow: inset 0 -2px 0 var(--accent); }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .graph { padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
  .plot { height: min(40dvh, 360px); }
  .levels { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: var(--gap); }
  .tile { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
  .tile .head { justify-content: flex-start; }
  .swatch { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .val { font-size: 32px; font-weight: 500; }
  .val small { font-size: 15px; color: var(--muted); }
  .pm { display: flex; gap: 8px; }
  .pm button { flex: 1; font-size: 24px; }
  .actions { display: flex; flex-wrap: wrap; gap: var(--gap); }
  .actions button { flex: 1 1 200px; }
  button[disabled] { opacity: .45; cursor: default; }
  @media (horizontal-viewport-segments: 2) {
    .drive { max-width: none; display: grid; grid-template-columns: env(viewport-segment-width 0 0) env(viewport-segment-width 1 0);
             column-gap: calc(env(viewport-segment-left 1 0) - env(viewport-segment-right 0 0)); padding-inline: 0; }
    .seg, .graph { grid-column: 1; }
    .levels, .actions { grid-column: 2; }
  }
</style>
