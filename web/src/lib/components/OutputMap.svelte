<script lang="ts">
  import { tick } from 'svelte'
  import { app } from '../state.svelte'
  import { workstationRequest } from '../http'
  import { fmtHz } from '../dsp'
  import type { Role, Source } from '../types'
  import { ROLE_COLORS, ROLE_LABEL, SOURCE_LABEL, sourceOf } from '../types'
  import { routeLabel, setupChanges, setupMix, type OutputDraft, type OutputSetupReview } from '../outputs'

  const roles: Role[] = ['tweeter', 'midrange', 'midbass', 'woofer', 'subwoofer', 'fullrange', 'unused']
  const channels = $derived((app.tune?.channels ?? []).slice().sort((a, b) => a.id.localeCompare(b.id)))
  let review = $state<OutputSetupReview | null>(null)
  let draft = $state<OutputDraft>({ name: '', role: 'unused', source: 'off' })
  let stage = $state<'edit' | 'review'>('edit')
  let busy = $state(false)
  let error = $state('')
  let dialog: HTMLDialogElement
  let editorHeading = $state<HTMLHeadingElement>()
  let nameInput = $state<HTMLInputElement>()
  async function changeStage(next: typeof stage) {
    stage = next; error = ''
    await tick()
    if (next === 'review') editorHeading?.focus()
    else nameInput?.focus()
  }
  const changes = $derived(review ? setupChanges(review.channel, draft) : [])
  const drivers = (cid: string) => (app.design?.components ?? []).filter(c => ['speaker', 'subwoofer'].includes(c.kind) && c.channels.includes(cid))
  const pending = (cid: string) => Object.values(app.protectionConstraints).filter(c => c.output === cid && c.state === 'pending').length

  $effect(() => {
    if (review && !dialog.open) dialog.showModal()
    if (!review && dialog.open) dialog.close()
  })
  async function openOutput(cid: string) {
    busy = true; error = ''
    try {
      const result = await workstationRequest<OutputSetupReview>('GET', `/api/outputs/${cid}/setup`)
      draft = { name: result.channel.name, role: result.channel.role, source: sourceOf(result.channel.mix) }
      stage = 'edit'; review = result
    } catch (e: any) { error = e.message }
    finally { busy = false }
  }
  async function save() {
    if (!review) return
    busy = true; error = ''
    try {
      await workstationRequest('PUT', `/api/outputs/${review.channel.id}/setup`, {
        name: draft.name, role: draft.role, mix: setupMix(draft.source, review.channel.mix), expected_context: review.context,
      })
      review = null
      app.toast('Output setup updated. Undo is available.', 'info')
    } catch (e: any) { error = e.message }
    finally { await app.poll(); busy = false }
  }
</script>

<section class="output-map" aria-labelledby="output-map-title">
  <div><h2 id="output-map-title">Map your physical outputs</h2><p class="muted">Follow the DSP’s A–J sockets. Names and role labels do not verify wiring or silence an output. Review the input route and recorded driver before tuning.</p></div>
  <div class="outputs">
    {#each channels as channel (channel.id)}
      {@const assigned = drivers(channel.id)}
      {@const limits = app.protections[channel.id]}
      <article class="panel output" aria-label="Output {channel.id}">
        <div class="identity"><b class="socket" style="border-color:{ROLE_COLORS[channel.role]}">{channel.id}</b><div><h3>{channel.name || 'Unnamed output'}</h3><span class="muted">{ROLE_LABEL[channel.role]} · {channel.mute ? 'Muted in tune' : 'Not muted in tune'} · {routeLabel(channel.mix)}</span></div></div>
        <dl>
          <div><dt>Recorded driver</dt><dd>{assigned.map(c => c.name || [c.make, c.model].filter(Boolean).join(' ') || 'Unnamed driver').join(' + ') || 'Not recorded'}</dd></div>
          <div><dt>Filters in tune</dt><dd>{channel.hp ? `HP ${fmtHz(channel.hp.freq_hz)}` : 'No high-pass'} · {channel.lp ? `LP ${fmtHz(channel.lp.freq_hz)}` : 'No low-pass'}</dd></div>
          <div><dt>Output limits</dt><dd>{limits?.min_hp_hz ? `HP ≥ ${fmtHz(limits.min_hp_hz)}` : 'No recorded HP floor'}{limits?.max_lp_hz ? ` · LP ≤ ${fmtHz(limits.max_lp_hz)}` : ''}{pending(channel.id) ? ` · ${pending(channel.id)} pending review` : ''}</dd></div>
        </dl>
        {#if channel.role === 'unused' && !channel.mute && sourceOf(channel.mix) !== 'off'}<p class="attention">Unused label still routes audio in this tune.</p>{/if}
        <button disabled={busy} aria-label="Edit output {channel.id} setup" onclick={() => openOutput(channel.id)}>Edit name, role & route…</button>
      </article>
    {/each}
  </div>
  {#if error && !review}<p role="alert">{error}</p>{/if}
</section>

<dialog bind:this={dialog} aria-labelledby="output-editor-title" onclose={() => { review = null; error = '' }} oncancel={(event) => { if (busy) event.preventDefault() }}>
  {#if review}
    <h2 id="output-editor-title" tabindex="-1" bind:this={editorHeading}>{stage === 'edit' ? 'Set up' : 'Review'} output {review.channel.id}</h2>
    <p>{review.live ? 'Routing changes will be sent to the connected DSP when you apply.' : 'Changes will be saved in the workstation. They will not be sent to the DSP.'}</p>
    {#if stage === 'edit'}
      <label>Output name<input maxlength="120" bind:this={nameInput} bind:value={draft.name} /></label>
      <label>Driver role<select bind:value={draft.role}>{#each roles as role}<option value={role}>{ROLE_LABEL[role]}</option>{/each}</select></label>
      <label>Input route<select bind:value={draft.source}>
        {#each ['L', 'R', 'mono', 'off'] as source}<option value={source}>{SOURCE_LABEL[source as Source]}</option>{/each}
        {#if sourceOf(review.channel.mix) === 'custom'}<option value="custom">Keep {routeLabel(review.channel.mix)}</option>{/if}
      </select></label>
      <p class="muted">Role changes must satisfy existing output limits and driver rules. To change crossover settings, use Studio. Driver identity and wiring are recorded separately in System.</p>
    {:else}
      <dl class="changes">{#each changes as change}<div><dt>{change.label}</dt><dd><span class="muted">{change.before}</span> → <strong>{change.after}</strong></dd></div>{/each}</dl>
      <p class="muted">Gain, mute, delay and filters remain as shown in the current tune. This does not confirm the physical wiring.</p>
    {/if}
    {#if error}<p role="alert">{error}</p>{/if}
    <div class="actions">
      <button disabled={busy} onclick={() => review = null}>Cancel</button>
      {#if stage === 'review'}<button disabled={busy} onclick={() => changeStage('edit')}>Back to edit</button><button class="primary" disabled={busy} onclick={save}>{busy ? 'Saving…' : review.live ? 'Apply to workstation & DSP' : 'Save in workstation'}</button>
      {:else}<button class="primary" disabled={!changes.length || busy} onclick={() => changeStage('review')}>Review changes</button>{/if}
    </div>
  {/if}
</dialog>

<style>
  .output-map { display: grid; gap: 14px; }
  h2 { font-size: 19px; margin: 0 0 8px; }
  p { line-height: 1.5; font-size: 13px; }
  .outputs { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 10px; }
  .output { padding: 14px; display: flex; flex-direction: column; align-items: start; gap: 12px; min-width: 0; }
  .identity { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .identity > div { min-width: 0; overflow-wrap: anywhere; }
  .identity span { font-size: 12px; }
  h3 { margin: 0 0 4px; font-size: 15px; }
  .socket { flex: none; border: 2px solid; border-radius: 8px; padding: 8px 12px; font: 18px var(--mono); }
  dl { display: grid; gap: 8px; margin: 0; width: 100%; overflow-wrap: anywhere; }
  dt { color: var(--muted); font-size: 12px; }
  dd { margin: 2px 0 0; font-size: 13px; }
  .output button { margin-top: auto; }
  .attention { color: var(--warn); margin: 0; }
  dialog { width: min(560px, calc(100vw - 24px)); max-height: 85dvh; overflow-y: auto; box-sizing: border-box; background: var(--panel); color: var(--ink); border: 1px solid var(--line-2); border-radius: var(--radius); padding: 22px; }
  dialog::backdrop { background: rgb(0 0 0 / .55); backdrop-filter: blur(3px); }
  label { display: grid; gap: 6px; margin-block: 14px; font-size: 14px; }
  input, select { min-width: 0; width: 100%; box-sizing: border-box; }
  .changes { gap: 14px; }
  .actions { display: flex; flex-wrap: wrap; justify-content: end; gap: 8px; margin-top: 18px; }
  [role='alert'] { color: var(--warn); }
</style>
