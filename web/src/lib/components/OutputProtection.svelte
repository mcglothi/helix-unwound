<script lang="ts">
  import { app } from '../state.svelte'
  let { cid }: { cid: string } = $props()
  const guard = $derived(app.protections[cid])
  const connected = $derived(!!app.status && app.status.device.kind !== 'none')
  let hp = $state<number | undefined>()
  let lp = $state<number | undefined>()
  let slope = $state(12)
  let factor = $state(0)
  $effect(() => {
    hp = guard?.min_hp_hz ?? undefined
    lp = guard?.max_lp_hz ?? undefined
    slope = guard?.min_hp_slope_db ?? 12
    factor = guard?.fs_factor ?? 0
  })
  function save(event: SubmitEvent) {
    event.preventDefault()
    if (connected || !confirm(`Reconfigure physical output ${cid}? Verify the connected driver. Tune labels and equipment specifications can still impose stricter limits.`)) return
    app.configureProtection(cid, { min_hp_hz: hp ?? null, min_hp_slope_db: slope, max_lp_hz: lp ?? null, fs_factor: factor })
  }
</script>

{#if guard}
  <details class="protection">
    <summary>Output {cid} protection · {guard.min_hp_hz ? `HP ≥ ${guard.min_hp_hz} Hz` : 'no HP minimum'}</summary>
    <p class="muted">These limits persist across role changes, scenes, and removed specifications. Disconnect the DSP before reconfiguring them.</p>
    <form onsubmit={save}>
      <fieldset disabled={connected}>
        <label>Minimum high-pass (Hz)<input type="number" min="10" max="24000" step="any" placeholder="none" bind:value={hp} /></label>
        <label>Minimum slope (dB/oct)<input type="number" min="6" max="48" step="6" bind:value={slope} required /></label>
        <label>Maximum low-pass (Hz)<input type="number" min="10" max="24000" step="any" placeholder="none" bind:value={lp} /></label>
        <label>Fs multiplier<input type="number" min="0" max="10" step="any" bind:value={factor} required /></label>
        <button type="submit">Save output limits…</button>
      </fieldset>
    </form>
  </details>
{/if}

<style>
  .protection { padding: 12px 0; border-top: 1px solid var(--line); }
  summary { cursor: pointer; font-size: 13px; }
  p { font-size: 13px; line-height: 1.5; }
  fieldset { border: 0; padding: 0; display: grid; gap: 8px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
</style>
