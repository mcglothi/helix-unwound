<script lang="ts">
  import { app } from '../state.svelte'
  import { workstationRequest } from '../http'
  import { canOverwrite, connectionStatus, deviceRequest, type Port, type OverwriteReview } from '../device'
  let { open = $bindable(false) }: { open?: boolean } = $props()
  let dialog: HTMLDialogElement
  let ports = $state<Port[]>([])
  let port = $state('')
  let writes = $state(false)
  let busy = $state(false)
  let error = $state('')
  let review = $state<OverwriteReview | null>(null)
  let confirmation = $state('')
  let storedBackup = $state<{id: string; bytes: number; xml_bytes: number; sha256: string; xml_sha256: string} | null>(null)
  let sceneName = $state('Stored preset backup')
  let importedScene = $state('')
  let importWarnings = $state<string[]>([])
  let importAdvisories = $state<string[]>([])
  const physicalWrites = $derived(!!app.status?.physical_writes_allowed)
  $effect(() => { if (port !== 'emulator' && !physicalWrites) writes = false })
  const device = $derived(app.status?.device)
  const connected = $derived(!!device && device.kind !== 'none')
  const ready = $derived(canOverwrite(review, app.status, confirmation))
  $effect(() => {
    if (open && !dialog.open) {
      dialog.showModal()
      review = null; confirmation = ''; writes = false; error = ''; storedBackup = null; importedScene = ''; importWarnings = []; importAdvisories = []
      void refreshPorts()
    }
    if (!open && dialog.open) dialog.close()
  })
  async function refreshPorts() {
    busy = true; error = ''
    try { ports = await deviceRequest<Port[]>('GET', '/api/ports') }
    catch (e: any) { error = e.message }
    finally { busy = false }
  }
  async function act(path: string, body?: unknown) {
    busy = true; error = ''
    try {
      await deviceRequest('POST', path, body)
      review = null; confirmation = ''
      if (path.endsWith('/disconnect')) writes = false
    } catch (e: any) { error = e.message }
    finally { await app.poll(); busy = false }
  }
  async function backupStored() {
    busy = true; error = ''; storedBackup = null; importedScene = ''; importWarnings = []; importAdvisories = []
    try { storedBackup = await workstationRequest('POST', '/api/device/stored-preset/backup') }
    catch (e: any) { error = e.message }
    finally { busy = false }
  }
  async function importStored() {
    if (!storedBackup) return
    busy = true; error = ''
    try {
      const result = await workstationRequest<{snapshot: string; warnings: string[]; safety_problems: string[]; safety_advisories?: string[]}>('POST', `/api/backups/stored/${storedBackup.id}/import`, {name: sceneName})
      importedScene = result.snapshot
      importWarnings = [...result.warnings, ...result.safety_problems]
      importAdvisories = result.safety_advisories ?? []
    } catch (e: any) { error = e.message }
    finally {
      try { await app.refresh() }
      catch { error = error || 'Could not refresh the workstation. Check the connection before retrying.' }
      busy = false
    }
  }
  async function prepare() {
    busy = true; error = ''; confirmation = ''
    try { review = await deviceRequest<OverwriteReview>('GET', '/api/device/review') }
    catch (e: any) { error = e.message }
    finally { busy = false }
  }
</script>

<dialog bind:this={dialog} onclose={() => open = false} aria-labelledby="connection-title">
  <div class="head"><h2 id="connection-title">Connection & recovery</h2><button aria-label="Close connection panel" onclick={() => open = false}>Close</button></div>
  <div class="connection-status"><strong>{connectionStatus(app.status)}</strong><span>{device?.model ?? 'Choose a device to begin'}</span></div>
  {#if app.status?.demo}<p class="notice">Demo: only the in-memory emulator is available.</p>
  {:else if physicalWrites}<p class="notice" role="alert">Supervised write mode: this server may send changes to a real DSP. Lower the volume, read the Director’s Digital Volume before and after, and keep PC-Tool closed. Only capture-verified settings are sent.</p>
  {:else}<p class="notice">Physical connections allow identification and explicit stored-preset backups. Hardware writes are off unless the server is started with --allow-physical-writes. Connecting does not read or back up the current DSP tune.</p>{/if}
  {#if !connected}
    <label>Device<select bind:value={port} disabled={busy}>
      <option value="">Choose a device…</option><option value="emulator">In-memory emulator</option>
      {#each ports as item}<option value={item.device}>{item.device} · {item.description}</option>{/each}
    </select></label>
    <button disabled={busy} onclick={refreshPorts}>Refresh ports</button>
    {#if !ports.length && !app.status?.demo}<p class="muted">No serial ports found. Check power, USB cable and operating-system access, then refresh. The emulator works without hardware.</p>{/if}
    <label class="check"><input type="checkbox" bind:checked={writes} disabled={busy || (port !== 'emulator' && !physicalWrites)} />Allow this workstation to send changes</label>
    <p class="muted">Start read-only to check the connection. Sending changes requires reviewing the workstation tune first.</p>
    <button disabled={!port || busy} onclick={() => act('/api/device/connect', { port, allow_writes: writes })}>{writes ? 'Connect with writes enabled' : 'Connect read-only'}</button>
  {:else}
    <p>{device?.baselined ? 'Changes are sent as you edit.' : 'Edits stay in the workstation until you send a reviewed tune.'}</p>
    {#if device?.sync_state === 'uncertain'}<p role="alert">Device state is unknown after an interrupted write. Incremental writes are paused. Review and overwrite all managed parameters to recover.</p>{/if}
    {#if device?.last_error}<p role="alert">{device.last_error}</p>{/if}
    <p class="muted">Disconnect does not mute or silence a running DSP. To change access mode, disconnect and reconnect.</p>
    <button disabled={busy} onclick={() => act('/api/device/disconnect')}>Disconnect</button>
    {#if device?.kind === 'serial'}
      <section class="stored">
        <h3>Back up the stored preset</h3>
        <p>Read the saved preset into a local backup. Unsaved DSP changes may differ. This does not load or apply a tune.</p>
        <button disabled={busy} onclick={backupStored}>Read & back up stored preset</button>
        {#if storedBackup}
          <p role="status">Backup saved · {storedBackup.bytes.toLocaleString()} bytes</p>
          <a href={`/api/backups/stored/${storedBackup.id}`} download>Download .afpx backup</a>
          <details><summary>Backup details</summary><p>{storedBackup.xml_bytes.toLocaleString()} XML bytes · two matching reads</p><p class="hash">Backup SHA256 {storedBackup.sha256}</p><p class="hash">XML SHA256 {storedBackup.xml_sha256}</p></details>
          <label>Scene name<input maxlength="120" bind:value={sceneName} disabled={busy} /></label>
          <button disabled={busy || !sceneName.trim()} onclick={importStored}>Copy backup to a scene</button>
          {#if importedScene}<p role="status">Scene “{importedScene}” created. It has not been loaded or sent to the DSP.</p>{/if}
          {#each importWarnings as warning}<p class="muted">{warning}</p>{/each}
          {#each importAdvisories as advisory}<p class="advisory" role="status">⚠ {advisory}</p>{/each}
        {/if}
      </section>
    {/if}
    {#if device?.writes_enabled}
      <button disabled={busy} onclick={prepare}>Review full overwrite…</button>
      {#if review}
        <section class="review">
          <h3>Overwrite {review.device.model ?? review.device.kind}</h3>
          <p>Replace the device’s active settings with <strong>{review.tune_name}</strong>. Save a backup of the existing device tune with the vendor software first.</p>
          {#if review.physical}
            <p role="alert">Live DSP on {review.device.port}: sound changes immediately. Settings go to the DSP’s working memory, not its stored preset, and stay until PC-Tool reloads a preset. Keep the volume low.</p>
            {#each review.excluded ?? [] as item}<p class="muted">Not sent: {item}</p>{/each}
            {#each review.ineligible ?? [] as item}<p role="alert">Cannot send: {item}</p>{/each}
          {/if}
          <details><summary>Overwrite details</summary><p>{review.parameter_count} managed parameters{review.physical ? ' (minus the exclusions above)' : ''} will be sent. This operation does not create a backup or write firmware. Completed requests are not independent readback verification.</p></details>
          <p class="muted">If this tune or connection changes, review it again before sending.</p>
          {#each review.problems as problem}<p role="alert">{problem}</p>{/each}
          {#if review.revision !== app.status?.revision || review.connection_epoch !== app.status?.connection_epoch}<p role="alert">Workstation changed. Review the overwrite again.</p>{/if}
          <label>Type OVERWRITE to confirm<input bind:value={confirmation} autocomplete="off" spellcheck="false" disabled={busy} /></label>
          <button disabled={busy || !ready} onclick={() => act('/api/device/push-full', { confirm: confirmation, expected_context: review!.context })}>Send reviewed tune</button>
        </section>
      {/if}
    {/if}
  {/if}
  {#if error}<p role="alert">{error}</p>{/if}
  {#if busy}<p role="status">Working…</p>{/if}
</dialog>
<style>
  .advisory { color: var(--caution); font-size: 12px; }
  dialog { width: min(600px, calc(100vw - 32px)); max-height: 85dvh; overflow-y: auto; padding: 24px; box-sizing: border-box; background: var(--panel); color: var(--ink); border: 1px solid var(--line-2); border-radius: var(--radius); box-shadow: 0 24px 80px rgb(0 0 0 / .35); }
  dialog::backdrop { background: rgb(0 0 0 / .55); backdrop-filter: blur(3px); }
  .stored { margin-block: 18px; padding-block: 14px; border-block: 1px solid var(--line); display: grid; gap: 12px; }
  .stored h3, .stored p { margin: 0; }
  .stored a { color: var(--accent-text); }
  .hash { overflow-wrap: anywhere; font: 12px var(--mono); }
  .head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
  .connection-status { display: grid; gap: 6px; padding: 16px 0; }
  .connection-status strong { color: var(--accent-text); }
  .connection-status span { color: var(--muted); }
  h2 { margin: 0; } p { line-height: 1.5; } label { display: grid; gap: 6px; margin: 14px 0; }
  .check { display: flex; align-items: center; } .check input { width: auto; }
  button { margin: 4px 6px 4px 0; } .notice, .review { padding: 12px; border: 1px solid var(--line); border-radius: 8px; }
</style>
