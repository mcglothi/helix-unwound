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
  let source = $state<'rew' | 'external'>('external')
  let level = $state(-24)
  let error = $state('')
  let busy = $state(false)
  let mode = $state<'measure' | 'align'>('measure')
  let reference = $state('')
  let adjust = $state('')
  let carry = $state<string[]>([])
  let steps = $state(9)
  let stepSeconds = $state(6)

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
  async function startAlign() {
    busy = true; error = ''
    try {
      await request('POST', '/api/measure/align', { reference, adjust, carry, seat, steps, seconds: stepSeconds,
                                                    level_dbfs: level, source })
    } catch (e: any) { error = e.message }
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
  {:else if running && run && run.kind === 'align' && run.align}
    <section class="live" aria-live="polite">
      <p class="step">Aligning <strong>{nameOf(run.align.adjust)}</strong> to <strong>{nameOf(run.align.reference)}</strong> at {run.align.fc} Hz
        · step {run.step + 1} of {run.align.offsets.length * 2}{run.step >= run.align.offsets.length ? ' (polarity flipped)' : ''}</p>
      <p class="phase">{PHASE[run.phase] === PHASE.averaging ? 'Measuring — hold the mic still at your head' : (PHASE[run.phase] ?? run.phase)}</p>
      {#if run.phase === 'averaging'}<p class="count mono">{Math.ceil(run.remaining_s)}<small> s</small></p>{/if}
      {#if run.align.results.length}
        <div class="bars">{#each run.align.results as r}
          {@const lo = Math.min(...run.align.results.map((x) => x.band_db))}
          <div class="bar"><span class="mono">{r.offset_ms > 0 ? '+' : ''}{r.offset_ms.toFixed(2)}{r.inverted ? ' ⇅' : ''}</span>
            <i style="width:{Math.max(4, (r.band_db - lo + 1) * 12)}px"></i><span class="mono">{r.band_db.toFixed(1)} dB</span></div>
        {/each}</div>
      {/if}
      <p class="muted">Keep the mic still at your head position for every step, so only the delay changes between them.</p>
      <button class="stop" onclick={stop}>Stop</button>
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
        <h3>{run.status === 'done' ? (run.kind === 'align' ? 'Alignment measured' : `Measured ${run.captures.length} output(s)`) : run.status === 'stopped' ? 'Stopped' : 'Run failed'}</h3>
        {#if run.kind === 'align' && run.align?.outcome}<p>{run.align.outcome}</p>{/if}
        {#if run.captures.length}<p>{run.captures.map((c) => c.output).join(', ')} added to your measurements and the estimate.</p>{/if}
        {#if run.error}<p>{run.error}</p>{/if}
      </section>
    {/if}
    {#if !synced}<p class="muted">Connect to the DSP with writes enabled and send your tune first; each output is isolated by muting the others.</p>{/if}
    <div class="row modes" role="group" aria-label="What to do">
      <button class:on={mode === 'measure'} aria-pressed={mode === 'measure'} onclick={() => mode = 'measure'}>Measure outputs</button>
      <button class:on={mode === 'align'} aria-pressed={mode === 'align'} onclick={() => mode = 'align'}>Time alignment</button>
    </div>
    {#if mode === 'align'}
    <fieldset disabled={busy || !synced}>
      <legend>Align a crossover pair</legend>
      <p class="muted">Plays the two outputs together and steps one output's delay a fraction of a millisecond at a time — once with its polarity as set and once flipped — keeping the setting where they add up most fully through their crossover. A flip that wins usually means a speaker is wired backwards. The result is a proposal you review; nothing changes by itself.</p>
      <label>Reference (stays as is)<select bind:value={reference}><option value="">Choose…</option>{#each playing as c}<option value={c.id}>{nameOf(c.id)}</option>{/each}</select></label>
      <label>Adjust this output's delay<select bind:value={adjust}><option value="">Choose…</option>{#each playing.filter((c) => c.id !== reference) as c}<option value={c.id}>{nameOf(c.id)}</option>{/each}</select></label>
      <div><span class="muted">Move these with it (keeps pairs you've already aligned together)</span>
        <div class="outs">{#each playing.filter((c) => c.id !== reference && c.id !== adjust) as c}<label><input type="checkbox" bind:group={carry} value={c.id} />{nameOf(c.id)}</label>{/each}</div></div>
      <label>Listening position<select bind:value={seat}><option value="driver">Driver</option><option value="passenger">Passenger</option><option value="center">Center</option></select></label>
      <label>Steps<select bind:value={steps}>{#each [7, 9, 13, 17] as n}<option value={n}>{n}</option>{/each}</select></label>
      <label>Averaging per step<select bind:value={stepSeconds}>{#each [4, 6, 8, 12] as n}<option value={n}>{n} seconds</option>{/each}</select></label>
      <label>Pink noise<select bind:value={source}>
        <option value="external">I'll play it from my phone (the way I normally listen)</option>
        <option value="rew">REW plays it from the Mac (e.g. Bluetooth to SYNC)</option>
      </select></label>
      <p class="muted">Hold the mic still at your head position for the whole sweep. Both outputs need a shared crossover (one's low-pass meeting the other's high-pass).</p>
      <button class="primary" disabled={!reference || !adjust} onclick={startAlign}>Start alignment: {steps * 2 + 3} measurements, about {Math.ceil((steps * 2 + 3) * (stepSeconds + 1) / 60)} min</button>
    </fieldset>
    {:else}
    <fieldset disabled={busy || !synced}>
      <legend>Which outputs?</legend>
      <div class="row">{#each presets as p}<button class:on={p.ids.join() === chosen.join()} onclick={() => chosen = [...p.ids]}>{p.l}</button>{/each}</div>
      <div class="outs">{#each playing as c}<label><input type="checkbox" bind:group={chosen} value={c.id} />{nameOf(c.id)}</label>{/each}</div>
      <label>Listening position<select bind:value={seat}><option value="driver">Driver</option><option value="passenger">Passenger</option><option value="center">Center</option></select></label>
      <label>Averaging per output<select bind:value={seconds}>{#each [10, 15, 20, 30, 45] as s}<option value={s}>{s} seconds</option>{/each}</select></label>
      <label>Pink noise<select bind:value={source}>
        <option value="external">I'll play it from my phone (the way I normally listen)</option>
        <option value="rew">REW plays it from the Mac (e.g. Bluetooth to SYNC)</option>
      </select></label>
      {#if source === 'external'}<p class="muted">Start a full-range pink noise track on your phone before you press Start, and keep it playing until the run finishes. A reference file from REW (Generator → pink noise → save as WAV) is more trustworthy than streaming tracks, which are often filtered.</p>{/if}
      {#if source === 'rew'}<label>REW level<select bind:value={level}>{#each [-36, -30, -24, -18, -12] as l}<option value={l}>{l} dBFS</option>{/each}</select></label>{/if}
      <p class="muted">Start with the volume low and raise it until the measurement is well above the cabin noise. Each output plays alone; the DSP's crossovers stay in place. Results are magnitude only (no timing or phase).</p>
      <button class="primary" disabled={!chosen.length} onclick={start}>Start: {chosen.length} output(s), about {Math.ceil(chosen.length * (seconds + 3) / 60)} min</button>
    </fieldset>
    {/if}
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
  .modes { margin: 12px 0; }
  .bars { display: grid; gap: 3px; justify-items: start; margin: 6px auto; }
  .bar { display: grid; grid-template-columns: 56px auto 64px; align-items: center; gap: 8px; font-size: 12px; }
  .bar i { display: block; height: 10px; background: var(--accent); border-radius: 3px; }
</style>
