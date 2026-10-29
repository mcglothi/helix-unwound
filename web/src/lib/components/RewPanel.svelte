<script lang="ts">
  import { app } from '../state.svelte'
  import { workstationRequest as request } from '../http'
  let { onimport }: { onimport: (id: string) => void | Promise<void> } = $props()
  interface RemoteCapture { uuid: string; title: string; date: string; notes: string; ambiguous: boolean }
  interface Preview { summary: RemoteCapture; fingerprint: string; points: number; frequency_range_hz: number[]; has_phase: boolean; smoothing: string; unit: string }
  let port = $state(4735)
  let rows = $state<RemoteCapture[] | null>(null)
  let preview = $state<Preview | null>(null)
  let channels = $state<string[]>([])
  let seat = $state('driver')
  let snapshot = $state('')
  const NOW = '__captured_now__'
  // "Captured just now" is offered only while a connected DSP is synchronized with this workstation.
  const canNow = $derived(!!app.status && app.status.device.kind !== 'none' && app.status.device.baselined &&
                          app.status.device.sync_state === 'synchronized')
  let confirmed = $state(false)
  let boundRevision = $state<number | null>(null)
  let boundEpoch = $state<number | null>(null)
  let busy = $state(false)
  let error = $state('')
  let info = $state('')
  function reset() { rows = null; preview = null; error = ''; info = '' }
  async function browse() {
    busy = true; error = ''; preview = null; info = ''
    try { rows = (await request<{measurements: RemoteCapture[]}>('GET', `/api/rew?port=${port}`)).measurements }
    catch (e: any) { error = e.message; rows = null }
    finally { busy = false }
  }
  async function inspect(row: RemoteCapture) {
    busy = true; error = ''; preview = null; info = ''; channels = []; confirmed = false
    snapshot = canNow ? NOW : ''
    // Bind to the workstation state when the capture is reviewed; any later change refuses import.
    boundRevision = app.status?.revision ?? null; boundEpoch = app.status?.connection_epoch ?? null
    try { preview = await request<Preview>('GET', `/api/rew/measurements/${row.uuid}?port=${port}`) }
    catch (e: any) { error = e.message }
    finally { busy = false }
  }
  async function save() {
    if (!preview) return
    busy = true; error = ''
    try {
      const now = snapshot === NOW
      const result = await request<{id: string; created: boolean}>('POST', '/api/rew/import', {
        port, uuid: preview.summary.uuid, expected_fingerprint: preview.fingerprint, channels, seat,
        ...(now ? { captured_now: true, owner_confirmed: confirmed, expected_revision: boundRevision,
                    expected_connection_epoch: boundEpoch }
                : { tune_snapshot: snapshot || null }),
      })
      preview = null
      info = !result.created ? 'This capture revision and assignment are already in your library.'
        : now ? 'Added with the tune on the DSP and the current drivers. It can be used for estimates and assisted tuning now.'
        : 'Copy added to your library. Review its capture hardware before assisted tuning.'
      await app.poll()
      await onimport(result.id)
    } catch (e: any) { error = e.message }
    finally { busy = false }
  }
</script>

<details class="rew">
  <summary>Bring measurements from REW</summary>
  <p>Open REW on the engine computer and enable its API in Preferences. Browse and copy existing captures here; REW’s measurements and audio settings stay unchanged.</p>
  <details><summary>Connection options</summary><label>Local REW API port<input type="number" min="1024" max="65535" bind:value={port} oninput={reset} disabled={busy} /></label></details>
  <button disabled={busy || !port} onclick={browse}>{busy ? 'Reading REW…' : 'Browse REW captures'}</button>
  {#if rows !== null && !rows.length}<p class="muted">REW is connected, but no measurements are loaded. Open a measurement in REW, then browse again.</p>{/if}
  {#if rows?.length}
    <div class="remote-list">{#each rows as row, i (`${row.uuid}:${i}`)}
      <button class="remote" disabled={busy || row.ambiguous} onclick={() => inspect(row)}>
        <strong>{row.title}</strong><span>{row.ambiguous ? 'Duplicate UUID in REW; keep one copy loaded' : row.date || 'Capture date not provided'}</span>
      </button>
    {/each}</div>
  {/if}
  {#if preview}
    <section class="preview">
      <h3>{preview.summary.title}</h3>
      <p>{preview.frequency_range_hz.map(n => Math.round(n)).join('–')} Hz · {preview.points} points · {preview.has_phase ? 'phase data included; timing not verified' : 'magnitude only'}</p>
      <fieldset disabled={busy}><legend>Which outputs were playing?</legend>
        <p class="muted">Leave unassigned if you don’t know. Labels are never inferred from the current installation.</p>
        <div class="outputs">{#each 'ABCDEFGHIJ'.split('') as cid}<label><input type="checkbox" bind:group={channels} value={cid} />{cid}</label>{/each}</div>
        <label>Listening position<select bind:value={seat}><option value="driver">Driver</option><option value="passenger">Passenger</option><option value="center">Center</option></select></label>
        <label>Capture-time tune<select bind:value={snapshot}>
          {#if canNow}<option value={NOW}>On the DSP now (just captured)</option>{/if}
          <option value="">Unknown · review later</option>{#each app.snapshots as name}<option value={name}>{name}</option>{/each}
        </select></label>
        {#if snapshot === NOW}
          <label class="confirm"><input type="checkbox" bind:checked={confirmed} />
            These outputs were playing the tune on the DSP, through the drivers currently recorded in Setup.</label>
          <p class="muted">This records your statement, not a hardware check: HelixTune only knows the settings the DSP acknowledged. Master gain isn’t sent to the DSP, and the Director or the head unit can change things outside HelixTune. If the tune or connection changes before you import, it’s refused.</p>
        {:else}
          <p class="muted">Only select a scene if you know it was active during capture. Import does not confirm driver identity.</p>
        {/if}
        <button disabled={snapshot === NOW && (!confirmed || !channels.length)} onclick={save}>Copy to measurement library</button>
      </fieldset>
    </section>
  {/if}
  {#if error}<p role="alert">{error}</p>{/if}
  {#if info}<p role="status">{info}</p>{/if}
</details>
<style>
  .rew { padding: 16px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); margin-bottom: 16px; }
  summary { cursor: pointer; font-weight: 500; } p { font-size: 13px; line-height: 1.5; }
  label { display: grid; gap: 6px; margin: 12px 0; } button { margin: 8px 0; }
  .remote-list { max-height: 260px; overflow-y: auto; display: grid; }
  .remote { display: grid; gap: 6px; text-align: left; width: 100%; overflow-wrap: anywhere; }
  .remote span { font-size: 12px; color: var(--muted); }
  .preview { padding: 12px; border: 1px solid var(--line); border-radius: 8px; margin-top: 12px; }
  fieldset { border: 0; padding: 0; min-width: 0; } .outputs { display: flex; flex-wrap: wrap; gap: 12px; }
  .outputs label { display: flex; align-items: center; gap: 6px; } .outputs input { width: auto; }
  .confirm { display: flex; align-items: flex-start; gap: 8px; } .confirm input { width: auto; margin-top: 3px; }
</style>
