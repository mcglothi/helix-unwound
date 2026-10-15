<script lang="ts">
  import { app } from '../state.svelte'
  import Designer from '../designer/Designer.svelte'
  import ComponentEditor from './ComponentEditor.svelte'

  const v = $derived(app.design?.vehicle)
  const missing = $derived(app.design?.components.filter((c) => ['speaker', 'subwoofer', 'amplifier', 'source'].includes(c.kind) && !c.model).length ?? 0)
  function setV(k: 'year' | 'make' | 'model' | 'trim', val: string) {
    if (v) app.setVehicle({ ...v, [k]: val })
  }
</script>

<div class="sys">
  <section class="panel top">
    <div class="vehicle">
      <span class="label">Vehicle</span>
      <input aria-label="Year" placeholder="Year" value={v?.year ?? ''} onchange={(e) => setV('year', e.currentTarget.value)} />
      <input aria-label="Make" placeholder="Make" value={v?.make ?? ''} onchange={(e) => setV('make', e.currentTarget.value)} />
      <input aria-label="Model" placeholder="Model" value={v?.model ?? ''} onchange={(e) => setV('model', e.currentTarget.value)} />
      <input aria-label="Trim / cab" placeholder="Trim / cab" value={v?.trim ?? ''} onchange={(e) => setV('trim', e.currentTarget.value)} />
    </div>
    <p class="muted tip">Drag between ports to wire · drop a wire on empty space to add a connected part · Delete removes the selection{missing ? ` · ${missing} parts still need a model` : ''}</p>
  </section>
  <div class="body">
    <section class="panel stage"><Designer /></section>
    <div class="editor"><ComponentEditor /></div>
  </div>
</div>

<style>
  .sys { display: flex; flex-direction: column; gap: var(--gap); padding: var(--gap); height: calc(100dvh - 60px); }
  .top { padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
  .vehicle { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .vehicle input { width: 120px; }
  .tip { margin: 0; font-size: 13px; }
  .body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: var(--gap); }
  .stage { overflow: hidden; min-height: 520px; }
  .editor { min-height: 0; display: flex; }
  .editor > :global(*) { flex: 1; }
  @media (max-width: 1100px) {
    .sys { height: auto; }
    .body { grid-template-columns: minmax(0, 1fr); }
    .stage { height: 70dvh; }
  }
  @media (horizontal-viewport-segments: 2) {
    .body { grid-template-columns: env(viewport-segment-width 0 0) env(viewport-segment-width 1 0);
            column-gap: calc(env(viewport-segment-left 1 0) - env(viewport-segment-right 0 0)); }
  }
</style>
