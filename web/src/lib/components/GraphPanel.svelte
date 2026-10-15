<script lang="ts">
  import { app } from '../state.svelte'
  import Graph from './Graph.svelte'

  const LAYERS = [
    { k: 'target', l: 'Target', sw: 'border-top:2px dashed var(--ink)' },
    { k: 'measured', l: 'Measured', sw: 'border-top:2px solid var(--dim)' },
    { k: 'predicted', l: 'Predicted', sw: 'border-top:3px solid var(--accent)' },
    { k: 'groups', l: 'Drivers', sw: 'border-top:2px solid var(--c-mid)' },
  ] as const
  const SEATS = ['driver', 'passenger', 'center']
</script>

<section class="panel gp">
  <div class="bar">
    <div class="seats" role="group" aria-label="Seat">
      {#each SEATS as s}
        <button class:on={app.seat === s} aria-pressed={app.seat === s} onclick={() => app.setSeat(s)}>{s}</button>
      {/each}
    </div>
    {#each LAYERS as L}
      <label class="layer"><input type="checkbox" bind:checked={app.layers[L.k]} /><span class="sw" style={L.sw}></span>{L.l}</label>
    {/each}
    <span class="spacer"></span>
    <label class="sm">Smoothing
      <select bind:value={app.smoothing} onchange={() => app.refresh()}>
        {#each [3, 6, 12, 24] as s}<option value={s}>1/{s} oct</option>{/each}
      </select>
    </label>
    <span class="mono muted tgt">Target: {app.system?.target_name ?? '—'}</span>
    <button class="small" disabled={app.busy || !app.system?.measurement_count} onclick={() => app.proposeAutoEq([app.selected])}>Auto-EQ {app.selected}</button>
    <button class="small" disabled={app.busy || !app.system?.measurement_count} onclick={() => app.proposeAutoEq(null)}>Auto-EQ all</button>
  </div>
  <div class="plot"><Graph /></div>
</section>

<style>
  .gp { padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; height: 100%; min-height: 360px; }
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; font-size: 13px; }
  .seats { display: flex; gap: 4px; }
  .seats button { min-height: 30px; font-size: 12px; text-transform: capitalize; }
  .layer { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); cursor: pointer; }
  .layer input { width: 14px; min-height: 0; }
  .sw { width: 18px; display: inline-block; }
  .spacer { flex: 1; }
  .sm { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); }
  .sm select { min-height: 30px; }
  .tgt { font-size: 12px; }
  .small { min-height: 30px; font-size: 12px; }
  .plot { flex: 1; min-height: 280px; }
</style>
