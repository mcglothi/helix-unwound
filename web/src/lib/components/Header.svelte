<script lang="ts">
  import { sessionRequest } from '../session'
  import { app, type Mode } from '../state.svelte'
  import { theme } from '../theme.svelte'
  import Settings from './Settings.svelte'

  let settingsOpen = $state(false)

  const dev = $derived(app.status?.device)
  const devText = $derived(
    !dev || dev.kind === 'none' ? 'Offline · editing only'
      : dev.sync_state === 'uncertain' ? `${dev.model ?? dev.kind} · state unknown`
      : `${dev.model ?? dev.kind} · ${dev.writes_enabled ? (dev.baselined ? 'LIVE' : 'not synced') : 'read-only'}`,
  )
  const ab = $derived(app.status?.ab)
  const live = $derived(!!dev?.writes_enabled && !!dev?.baselined)
  const MODES: { m: Mode; l: string }[] = [{ m: 'studio', l: 'Studio' }, { m: 'drive', l: 'Drive' }, { m: 'setup', l: 'Setup' }, { m: 'system', l: 'System' }, { m: 'measurements', l: 'Measurements' }]

  function setMode(m: Mode) {
    app.mode = m
    document.documentElement.dataset.mode = m
    theme.apply(m)
  }
  async function signOut() {
    try {
      const response = await sessionRequest('/api/session', { method: 'DELETE' })
      if (response.ok) location.reload()
      else app.toast('Could not end the session. Check the engine connection.')
    } catch { app.toast('Could not end the session. Check the engine connection.') }
  }
  function snapshot(e: Event) {
    const sel = e.currentTarget as HTMLSelectElement
    const v = sel.value
    sel.value = ''
    if (v === '__save') {
      const n = prompt('Save current tune as…')
      if (n) app.saveSnapshot(n)
    } else if (v === '__A' || v === '__B') {
      app.setAB(v === '__A' ? 'A' : 'B', null)
    } else if (v.startsWith('__A:') || v.startsWith('__B:')) {
      app.setAB(v[2] as 'A' | 'B', v.slice(4))
    } else if (v && confirm(`Load “${v}”? It goes live if the DSP is connected.`)) app.loadSnapshot(v)
  }
</script>

<header>
  <div class="brand">Helix <span>Unwound</span></div>
  <nav class="modes" aria-label="Mode">
    {#each MODES as { m, l }}
      <button class:active={app.mode === m} aria-pressed={app.mode === m} onclick={() => setMode(m)}>{l}</button>
    {/each}
  </nav>
  <span class="tune mono" title="Current tune">{app.tune?.name ?? '…'}</span>
  <span class="spacer"></span>
  <span class="pill mono" class:live>{devText}</span>
  <span class="pill mono">{app.system?.measurement_count ?? 0} measurements</span>
  <select aria-label="Scenes and snapshots" onchange={snapshot}>
    <option value="">Scenes…</option>
    {#each app.snapshots as s}<option value={s}>{s}</option>{/each}
    <option value="__save">Save current as…</option>
    <optgroup label="A/B compare">
      <option value="__A">Set A = current tune</option>
      <option value="__B">Set B = current tune</option>
      {#each app.snapshots as s}<option value="__B:{s}">Set B = {s}</option>{/each}
    </optgroup>
  </select>
  {#if ab?.A && ab?.B}
    <button class="ab" onclick={() => app.toggleAB()} title="A: {ab.A} · B: {ab.B}">
      <span class:on={ab.active === 'A'}>A</span><span class:on={ab.active === 'B'}>B</span>
    </button>
  {/if}
  <button aria-label="Appearance" title="Appearance" onclick={() => (settingsOpen = true)}>
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="13.5" cy="6.5" r="1.5"/><circle cx="17.5" cy="10.5" r="1.5"/><circle cx="8.5" cy="7.5" r="1.5"/><circle cx="6.5" cy="12.5" r="1.5"/><path d="M12 2a10 10 0 000 20c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A5.6 5.6 0 0022 9.8C22 5.5 17.5 2 12 2z"/></svg>
  </button>
  <button aria-label="Undo" title="Undo" onclick={() => app.undo()} disabled={!app.status?.undo_depth}>
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 010 12h-3"/></svg>
  </button>
  <button onclick={signOut}>Sign out</button>
</header>
{#if dev?.last_error}
  <div class="device-error" role="alert">{dev.last_error} Edits are staged offline until then.</div>
{/if}
{#if app.status?.demo}
  <div class="demo-banner" role="status"><strong>Demo workstation</strong> · Synthetic hardware and generated captures. Physical device connections are disabled.</div>
{/if}
<Settings bind:open={settingsOpen} />

<style>
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 5; }
  .demo-banner { padding: 8px 16px; color: var(--ink); background: var(--panel); border-bottom: 2px solid var(--accent); font-size: 13px; line-height: 1.5; }
  .device-error { padding: 12px 16px; color: var(--ink); background: var(--panel); border-bottom: 2px solid var(--warn); }
  .brand { font-weight: 600; font-size: 17px; letter-spacing: .02em; }
  .brand span { color: var(--accent-text); }
  .modes { display: flex; max-width: 100%; overflow-x: auto; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 3px; }
  .modes button { flex-shrink: 0; border: 0; background: transparent; color: var(--muted); min-height: calc(var(--tap) - 6px); }
  .modes button.active { background: var(--panel-2); color: var(--ink); }
  .tune { color: var(--muted); font-size: 13px; max-width: 28ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .spacer { flex: 1; }
  .pill { font-size: 12px; color: var(--muted); border: 1px solid var(--line-2); border-radius: 99px; padding: 4px 10px; }
  .pill.live { color: var(--ok); border-color: color-mix(in srgb, var(--ok) 50%, transparent); }
  button[disabled] { opacity: .4; cursor: default; }
  select { max-width: 170px; }
  .ab { display: inline-flex; gap: 2px; padding: 3px; font-weight: 600; }
  .ab span { padding: 4px 10px; border-radius: 4px; color: var(--muted); }
  .ab span.on { background: var(--accent); color: var(--accent-ink); }
  @media (max-width: 700px) { .tune, .pill:nth-of-type(2) { display: none; } }
</style>
