<script lang="ts">
  import { app } from '../state.svelte'
  import { workstationRequest as request } from '../http'
  import { ROLE_LABEL } from '../types'
  import type { Role } from '../types'
  let { open = $bindable(false) }: { open?: boolean } = $props()
  let dialog: HTMLDialogElement

  const FRONT: Role[] = ['tweeter', 'midrange', 'midbass', 'woofer', 'fullrange']
  const playing = $derived((app.tune?.channels ?? []).filter((c) => c.role !== 'unused' && !c.mute))
  const presets = $derived([
    { k: 'front', l: 'Front drivers', ids: playing.filter((c) => FRONT.includes(c.role)).map((c) => c.id) },
    { k: 'subs', l: 'Subwoofers', ids: playing.filter((c) => c.role === 'subwoofer').map((c) => c.id) },
    { k: 'all', l: 'Everything playing', ids: playing.map((c) => c.id) },
  ].filter((p) => p.ids.length))
  let chosen = $state<string[]>([])
  let seat = $state('driver')
  let seconds = $state(20)
  let source = $state<'rew' | 'external'>('rew')
  let level = $state(-24)
  let error = $state('')
  let busy = $state(false)

  const run = $derived(app.status?.measure_run ?? null)
  const running = $derived(run?.status === 'running')
  const interrupted = $derived(app.status?.interrupted_measure_run ?? null)
  const synced = $derived(!!app.status && app.status.device.kind !== 'none' && app.status.device.writes_enabled &&
                          app.status.device.baselined && app.status.device.sync_state === 'synchronized')
  const nameOf = (id: string) => {
    const c = app.tune?.channels.find((x) => x.id === id)
    return c ? `${id} · ${c.name || ROLE_LABEL[c.role]}` : id
  }
  const PHASE: Record<string, string> = {
    starting: 'Starting…', isolating: 'Muting the other outputs…', settling: 'Settling…',
    averaging: 'Measuring — move the mic slowly around your head', saving: 'Saving the average…',
    importing: 'Adding to your measurements…', restoring: 'Restoring the outputs…', done: 'Finished',
  }

  $effect(() => {
    if (open && !dialog.open) {
      dialog.showModal(); error = ''
      if (!chosen.length && presets[0]) chosen = [...presets[0].ids]
    }
    if (!open && dialog.open) dialog.close()
  })

  async function start() {
    busy = true; error = ''
    try { await request('POST', '/api/measure/runs', { outputs: chosen, seat, seconds, level_dbfs: level, source }) }
    catch (e: any) { error = e.message }
    finally { await app.poll(); busy = false }
  }
  async function stop() {
    try { await request('POST', '/api/measure/runs/current/stop') } catch (e: any) { error = e.message }
    await app.poll()
  }
  async function resolve(action: 'restore' | 'discard') {
    busy = true; error = ''
    try { await request('POST', '/api/measure/interrupted', { action }) } catch (e: any) { error = e.message }
    finally { await app.poll(); busy = false }
  }
</script>

<dialog bind:this={dialog} onclose={() => open = false} aria-labelledby="measure-title">
  <div class="head"><h2 id="measure-title">Measure this seat</h2>
    <button aria-label="Close" disabled={running} onclick={() => open = false}>Close</button></div>

  {#if interrupted}
    <section class="warn" role="alert">
      <h3>A measurement run was interrupted</h3>
      <p>{interrupted.error ?? `It may have left outputs ${(interrupted.changed ?? []).join(', ')} muted.`}</p>
      <div class="row">
        <button class="primary" disabled={busy || !synced} onclick={() => resolve('restore')}>Restore those mutes</button>
        <button disabled={busy} onclick={() => resolve('discard')}>Leave mutes as they are</button>
      </div>
      {#if !synced}<p class="muted">Connect and synchronize the DSP to restore.</p>{/if}
    </section>
  {:else if running && run}
    <section class="live" aria-live="polite">
      <p class="step">Output {run.step + 1} of {run.outputs.length}: <strong>{run.current ? nameOf(run.current) : ''}</strong></p>
      <p class="phase">{PHASE[run.phase] ?? run.phase}</p>
      {#if run.phase === 'averaging'}<p class="count mono">{Math.ceil(run.remaining_s)}<small> s</small></p>{/if}
      <p class="muted">Keep still. Move the microphone slowly around your head position, about a hand's width each way, pointing up.</p>
      <button class="stop" onclick={stop}>Stop</button>
    </section>
  {:else}
    {#if run && run.status !== 'running'}
      <section class={run.status === 'done' ? 'ok' : 'warn'} role="status">
        <h3>{run.status === 'done' ? `Measured ${run.captures.length} output(s)` : run.status === 'stopped' ? 'Stopped' : 'Run failed'}</h3>
        {#if run.captures.length}<p>{run.captures.map((c) => c.output).join(', ')} added to your measurements and the estimate.</p>{/if}
        {#if run.error}<p>{run.error}</p>{/if}
      </section>
    {/if}
    {#if !synced}<p class="muted">Connect to the DSP with writes enabled and send your tune first; each output is isolated by muting the others.</p>{/if}
    <fieldset disabled={busy || !synced}>
      <legend>Which outputs?</legend>
      <div class="row">{#each presets as p}<button class:on={p.ids.join() === chosen.join()} onclick={() => chosen = [...p.ids]}>{p.l}</button>{/each}</div>
      <div class="outs">{#each playing as c}<label><input type="checkbox" bind:group={chosen} value={c.id} />{nameOf(c.id)}</label>{/each}</div>
      <label>Listening position<select bind:value={seat}><option value="driver">Driver</option><option value="passenger">Passenger</option><option value="center">Center</option></select></label>
      <label>Averaging per output<select bind:value={seconds}>{#each [10, 15, 20, 30, 45] as s}<option value={s}>{s} seconds</option>{/each}</select></label>
      <label>Pink noise<select bind:value={source}>
        <option value="rew">REW plays it (Mac audio to the truck, e.g. Bluetooth to SYNC)</option>
        <option value="external">I'll play pink noise myself</option>
      </select></label>
      {#if source === 'rew'}<label>REW level<select bind:value={level}>{#each [-36, -30, -24, -18, -12] as l}<option value={l}>{l} dBFS</option>{/each}</select></label>{/if}
      <p class="muted">Start with the volume low and raise it until the measurement is well above the cabin noise. Each output plays alone; the DSP's crossovers stay in place. Results are magnitude only (no timing or phase).</p>
      <button class="primary" disabled={!chosen.length} onclick={start}>Start: {chosen.length} output(s), about {Math.ceil(chosen.length * (seconds + 3) / 60)} min</button>
    </fieldset>
  {/if}
  {#if error}<p role="alert">{error}</p>{/if}
</dialog>

<style>
  dialog { width: min(560px, calc(100vw - 32px)); max-height: 88dvh; overflow-y: auto; padding: 22px; box-sizing: border-box;
           background: var(--panel); color: var(--ink); border: 1px solid var(--line-2); border-radius: var(--radius); }
  dialog::backdrop { background: rgb(0 0 0 / .55); }
  .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  h2 { margin: 0; } h3 { margin: 0 0 6px; font-size: 15px; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 12px; min-width: 0; }
  legend { font-weight: 600; margin-bottom: 6px; }
  label { display: grid; gap: 4px; font-size: 13px; color: var(--muted); }
  .row { display: flex; flex-wrap: wrap; gap: 8px; }
  .row button.on { box-shadow: inset 0 -2px 0 var(--accent); }
  .outs { display: flex; flex-wrap: wrap; gap: 10px 16px; }
  .outs label { display: flex; align-items: center; gap: 6px; color: var(--ink); }
  .outs input { width: auto; }
  .live { text-align: center; padding: 18px 0; display: grid; gap: 10px; }
  .step { margin: 0; } .phase { margin: 0; font-weight: 600; }
  .count { font-size: 64px; line-height: 1; margin: 6px 0; } .count small { font-size: 20px; }
  .stop { justify-self: center; min-width: 160px; min-height: 52px; font-size: 18px; border-color: var(--warn); }
  .warn { border: 1px solid var(--caution); border-radius: 8px; padding: 12px; margin: 12px 0; }
  .ok { border: 1px solid var(--line-2); border-radius: 8px; padding: 12px; margin: 12px 0; }
  p { margin: 0; font-size: 13px; line-height: 1.5; }
</style>
