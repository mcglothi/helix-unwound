<script lang="ts">
  import { onMount } from 'svelte'
  import { app } from '../state.svelte'
  import { canRecordHardware, captureDraft, hardwareLabel, sameDrivers, type CaptureDrivers, type MeasurementRecord } from '../measurements'

  let records = $state<MeasurementRecord[]>([])
  let selected = $state<MeasurementRecord | null>(null)
  let draft = $state<CaptureDrivers>({})
  let reason = $state('')
  let reviewed = $state(false)
  let correction = $state(false)
  let busy = $state(false)
  let error = $state('')
  let name = $state('')
  let seat = $state('driver')
  let channels = $state<string[]>([])
  let snapshot = $state('keep')
  const correcting = $derived(!!selected?.drivers && !sameDrivers(selected.drivers, draft))
  const valid = $derived(canRecordHardware(selected, draft, reason, reviewed, correction))
  const ids = 'ABCDEFGHIJ'.split('')
  const date = (seconds: number) => seconds > 0 ? new Date(seconds * 1000).toLocaleString() : 'Capture date unknown'
  const label = (cid: string) => `${cid} · ${app.tune?.channels.find((c) => c.id === cid)?.name || 'Output'}`
  const driverNames = (drivers: CaptureDrivers | null, cid: string) =>
    drivers?.[cid]?.map((d) => `${d.make} ${d.model}`.trim() || 'Unidentified driver').join(', ') || 'Not recorded'

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(path, { method, headers: body === undefined ? {} : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body) })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`)
    return data
  }
  function select(record: MeasurementRecord | null) {
    selected = record
    draft = record ? captureDraft(record) : {}
    reason = ''; reviewed = false; correction = false; error = ''
    name = record?.name ?? ''; seat = record?.seat ?? 'driver'
    channels = [...(record?.channels ?? [])]; snapshot = 'keep'
  }
  async function refresh(preferred = selected?.id) {
    busy = true
    try {
      const next = await request<MeasurementRecord[]>('GET', '/api/measurements')
      records = next.slice().reverse()
      select(records.find((m) => m.id === preferred) ?? records[0] ?? null)
    } catch (e: any) { error = e.message ?? String(e) }
    finally { busy = false }
  }
  onMount(() => { void refresh() })

  function useCurrent() {
    if (!selected || !confirm('Only use the installed driver list if you have evidence that these exact drivers were installed when this measurement was captured. A later replacement does not update historical measurements.')) return
    draft = Object.fromEntries(selected.channels.map((cid) => [cid, (selected!.current_drivers[cid] ?? []).map((d) => ({ ...d }))]))
    reviewed = false; correction = false
  }
  function addDriver(cid: string) {
    draft[cid] = [...(draft[cid] ?? []), { id: `historical:${crypto.randomUUID()}`, make: '', model: '' }]
    reviewed = false
  }
  async function recordHardware(event: SubmitEvent) {
    event.preventDefault()
    if (!selected || !valid || busy) return
    busy = true; error = ''
    try {
      const updated = await request<MeasurementRecord>('POST', `/api/measurements/${selected.id}/attest`, {
        drivers: draft, reason: reason.trim(), expected_fingerprint: selected.capture_fingerprint, correct_existing: correction,
      })
      records = records.map((m) => m.id === updated.id ? updated : m)
      select(updated)
      app.toast('Capture-time hardware recorded. Historical hardware remains historical.', 'info')
      await app.poll()
    } catch (e: any) { error = e.message ?? String(e) }
    finally { busy = false }
  }
  async function saveDetails(event: SubmitEvent) {
    event.preventDefault()
    if (!selected || busy) return
    busy = true; error = ''
    try {
      const updated = await request<MeasurementRecord>('PATCH', `/api/measurements/${selected.id}`, {
        name, seat, channels, ...(snapshot === 'clear' ? { clear_tune: true } :
          snapshot === 'keep' ? {} : { tune_snapshot: snapshot }),
      })
      records = records.map((m) => m.id === updated.id ? updated : m)
      select(updated)
      app.toast('Capture details saved. Changed capture context requires hardware review.', 'info')
      await app.poll()
    } catch (e: any) { error = e.message ?? String(e) }
    finally { busy = false }
  }
</script>

<main class="library">
  <section class="panel listing">
    <div class="head"><div><h1>Measurements</h1><p class="muted">What was captured, and with which hardware.</p></div>
      <button disabled={busy} onclick={() => refresh()}>Refresh</button></div>
    {#if !records.length}<p class="muted">No measurements yet. Imported REW captures appear here for review.</p>{/if}
    <div class="rows">
      {#each records as record (record.id)}
        <button class="record" class:active={selected?.id === record.id} disabled={busy} onclick={() => select(record)}>
          <b>{record.name}</b><span>{record.channels.join(' + ') || 'Outputs not tagged'} · {record.seat}</span>
          <small>{date(record.taken_at)}</small><small>{hardwareLabel(record.status)}</small>
        </button>
      {/each}
    </div>
  </section>

  <section class="detail">
    {#if error}<div class="panel error" role="alert">{error} Your form has been retained; refresh to review the latest record.</div>{/if}
    {#if selected}
      <div class="panel overview">
        <div class="head"><h2>{selected.name}</h2><span class="badge" class:eligible={selected.optimizable}>{hardwareLabel(selected.status)}</span></div>
        <p class="muted">{date(selected.taken_at)} · {selected.kind} · {selected.source || 'Source not recorded'}</p>
        {#if selected.status_reason}<p>{selected.status_reason}</p>{/if}
        <p>{selected.optimizable ? 'Hardware and capture-time tune are recorded for assisted tuning.' :
          !selected.has_tune ? 'Capture-time tune is unknown. This capture cannot support assisted tuning yet.' :
          'This capture remains available as history; it is not eligible for assisted tuning of the installed drivers.'}</p>
        <p class="notice">A measurement taken before a driver replacement describes the old drivers. Recording hardware does not prove calibration, phase, or hardware-protocol accuracy.</p>
        <table><thead><tr><th>Output</th><th>Hardware at capture</th><th>Installed now</th></tr></thead><tbody>
          {#each selected.channels as cid}<tr><td>{cid}</td><td>{driverNames(selected.drivers, cid)}</td><td>{driverNames(selected.current_drivers, cid)}</td></tr>{/each}
        </tbody></table>
      </div>

      <details class="panel details">
        <summary>Capture details · {selected.tune_name ?? 'capture-time tune unknown'}</summary>
        <form onsubmit={saveDetails}>
          <label>Name<input bind:value={name} required /></label>
          <label>Seat<select bind:value={seat}>{#each ['driver', 'passenger', 'center', 'average'] as item}<option value={item}>{item}</option>{/each}</select></label>
          <fieldset><legend>Outputs playing during capture</legend><div class="tags">{#each ids as cid}
            <label><input type="checkbox" bind:group={channels} value={cid} />{label(cid)}</label>
          {/each}</div></fieldset>
          <label>Tune active during capture<select bind:value={snapshot}>
            <option value="keep">Keep {selected.tune_name ?? 'unknown baseline'}</option><option value="clear">Mark baseline unknown</option>
            {#each app.snapshots as item}<option value={item}>{item}</option>{/each}
          </select></label>
          <p class="muted">Choose a scene only if it was active during capture. Changing outputs, seat, or baseline clears hardware confirmation and preserves its history.</p>
          <button type="submit" disabled={busy}>Save capture details</button>
        </form>
      </details>

      <div class="panel evidence">
        <h2>Record capture-time hardware</h2>
        <p class="muted">Enter historical drivers below, or explicitly review the installed driver list. Nothing is prefilled from the current installation.</p>
        <button disabled={busy || !selected.channels.length} onclick={useCurrent}>Review installed drivers as capture hardware…</button>
        <form onsubmit={recordHardware}>
          {#each selected.channels as cid}
            <fieldset><legend>{label(cid)}</legend>
              {#each draft[cid] ?? [] as driver, i (driver.id)}
                <div class="driver-row"><label>Make<input bind:value={driver.make} oninput={() => reviewed = false} required maxlength="120" /></label>
                  <label>Model<input bind:value={driver.model} oninput={() => reviewed = false} required maxlength="120" /></label>
                  <button type="button" aria-label="Remove driver {i + 1} from output {cid}" disabled={busy} onclick={() => { draft[cid] = draft[cid].filter((_, n) => n !== i); reviewed = false }}>Remove</button></div>
              {/each}
              <button type="button" disabled={busy} onclick={() => addDriver(cid)}>Add historical driver</button>
            </fieldset>
          {/each}
          <label>Evidence and reason<textarea bind:value={reason} minlength="8" maxlength="2000" required placeholder="For example: capture notes and installation records identify the drivers installed on this date."></textarea></label>
          {#if correcting}<label class="check"><input type="checkbox" bind:checked={correction} />I am correcting an existing hardware record; retain the previous record and this reason.</label>{/if}
          <label class="check"><input type="checkbox" bind:checked={reviewed} />I reviewed the capture date, outputs, and evidence. These are the drivers used at capture time.</label>
          <button class="primary" type="submit" disabled={busy || !valid}>Record capture hardware</button>
        </form>
      </div>

      <details class="panel details"><summary>Hardware record history · {selected.driver_history.length}</summary>
        {#each selected.driver_history.slice().reverse() as entry}
          <div class="history"><b>{entry.action} · {date(entry.at)}</b><p>{entry.reason}</p>
            {#each Object.keys(entry.drivers ?? entry.previous_drivers ?? {}) as cid}<small>{cid}: {driverNames(entry.drivers ?? entry.previous_drivers, cid)}</small>{/each}
          </div>
        {/each}
        {#if !selected.driver_history.length}<p class="muted">No review history recorded yet.</p>{/if}
      </details>
    {/if}
  </section>
</main>

<style>
  .library { display: grid; grid-template-columns: minmax(240px, 320px) minmax(0, 1fr); gap: var(--gap); padding: var(--gap); max-width: 1500px; margin: auto; }
  .listing, .overview, .evidence, .details, .error { padding: 18px; }
  .detail, .rows, form { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .listing { align-self: start; }
  h1, h2 { margin: 0; } h1 { font-size: 23px; } h2 { font-size: 18px; }
  p { line-height: 1.5; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  .record { text-align: left; display: flex; flex-direction: column; gap: 6px; padding: 12px; }
  .record.active { border-color: var(--accent); background: var(--panel-2); }
  small, .record span { color: var(--muted); font-size: 12px; }
  .badge { font-size: 12px; border: 1px solid var(--muted); padding: 5px 8px; border-radius: 8px; }
  .eligible { border-color: var(--ok); }
  .notice { color: var(--muted); border-left: 2px solid var(--accent); padding-left: 12px; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; } th, td { text-align: left; padding: 10px 6px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
  summary { cursor: pointer; } details form { margin-top: 16px; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
  fieldset { border: 1px solid var(--line); padding: 12px; min-width: 0; border-radius: 8px; }
  legend { font-size: 13px; padding: 0 6px; }
  .driver-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; align-items: end; margin-bottom: 12px; }
  .driver-row input { width: 100%; min-width: 0; }
  .check, .tags label { flex-direction: row; align-items: flex-start; gap: 8px; }
  .check input, .tags input { width: 16px; min-height: 0; margin-top: 2px; }
  .tags { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }
  textarea { min-height: 90px; resize: vertical; }
  .history { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
  .history small { display: block; margin: 5px 0; }
  .error { border-color: var(--warn); }
  button:disabled { opacity: .5; cursor: default; }
  @media (max-width: 900px) { .library { grid-template-columns: 1fr; } .rows { max-height: 280px; overflow-y: auto; } }
  @media (max-width: 550px) { .driver-row { grid-template-columns: 1fr; } }
</style>
