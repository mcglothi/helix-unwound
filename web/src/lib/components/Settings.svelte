<script lang="ts">
  import { theme } from '../theme.svelte'
  import { parseBase16, tokens, type Scheme } from '../themes'

  let { open = $bindable(false) }: { open?: boolean } = $props()
  let yaml = $state('')
  let err = $state('')
  let dialog: HTMLDialogElement

  $effect(() => {
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  })

  async function importScheme() {
    err = ''
    try {
      const sc = parseBase16(yaml)
      if (theme.all.some((t) => t.builtin && t.name === sc.name)) sc.name += ' (imported)'
      await theme.save(sc)
      theme.choose(sc.name)
      yaml = ''
    } catch (e: any) {
      err = e.message ?? String(e)
    }
  }
  const sw = (sc: Scheme) => {
    const t = tokens(sc)
    return { bg: t['--bg'], panel: t['--panel'], ink: t['--ink'], muted: t['--muted'], accent: t['--accent'],
      drivers: [t['--c-sub'], t['--c-midbass'], t['--c-mid'], t['--c-tweeter']] }
  }
</script>

<dialog bind:this={dialog} onclose={() => (open = false)} aria-labelledby="settings-title">
  <header>
    <h2 id="settings-title">Appearance</h2>
    <button aria-label="Close" onclick={() => (open = false)}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
    </button>
  </header>

  <label class="inline"><input type="checkbox" checked={theme.followSystem} onchange={(e) => theme.setFollowSystem(e.currentTarget.checked)} />
    Follow system light/dark (Studio / Studio Light)</label>

  <div class="grid" role="radiogroup" aria-label="Theme">
    {#each theme.all as sc (sc.name)}
      {@const c = sw(sc)}
      <button role="radio" aria-checked={!theme.followSystem && theme.name === sc.name} class="card"
              class:sel={!theme.followSystem && theme.name === sc.name}
              style="background:{c.bg}; color:{c.ink}; border-color:{!theme.followSystem && theme.name === sc.name ? c.accent : c.panel}"
              onclick={() => theme.choose(sc.name)}>
        <span class="preview" style="background:{c.panel}">
          <span class="bar" style="background:{c.accent}"></span>
          {#each c.drivers as d}<span class="dot" style="background:{d}"></span>{/each}
        </span>
        <span class="nm">{sc.name}</span>
        <span class="by" style="color:{c.muted}">{sc.author ?? (sc.builtin ? '' : 'imported')}{sc.variant === 'light' ? ' · light' : ''}</span>
        {#if !sc.builtin}
          <span class="del" role="button" tabindex="0" aria-label="Delete {sc.name}"
                onclick={(e) => { e.stopPropagation(); theme.remove(sc.name) }}
                onkeydown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); theme.remove(sc.name) } }}>×</span>
        {/if}
      </button>
    {/each}
  </div>

  <label>Drive mode theme
    <select value={theme.driveName} onchange={(e) => theme.chooseDrive(e.currentTarget.value)}>
      <option value="">Same as the app</option>
      {#each theme.all as sc}<option value={sc.name}>{sc.name}</option>{/each}
    </select>
  </label>

  <details>
    <summary>Import a base16 scheme</summary>
    <p class="muted">Paste a base16 YAML scheme (from the tinted-theming / base16 schemes collections). It's saved on the engine so every device can use it.</p>
    <textarea bind:value={yaml} rows="9" placeholder={'scheme: "My Scheme"\nauthor: "me"\nbase00: "1d1f21"\n…\nbase0F: "a3685a"'}></textarea>
    {#if err}<p class="err">{err}</p>{/if}
    <button class="primary" disabled={!yaml.trim()} onclick={importScheme}>Import and use</button>
  </details>
</dialog>

<style>
  dialog { width: min(760px, calc(100vw - 32px)); max-height: calc(100dvh - 48px); background: var(--panel); color: var(--ink);
           border: 1px solid var(--line-2); border-radius: var(--radius); padding: 18px; }
  dialog::backdrop { background: rgb(0 0 0 / .55); }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  h2 { margin: 0; font-size: 18px; }
  label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); margin: 14px 0; }
  label.inline { flex-direction: row; align-items: center; gap: 8px; color: var(--ink); font-size: 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
  .card { position: relative; display: flex; flex-direction: column; align-items: stretch; gap: 6px; padding: 8px; text-align: left; border-width: 2px; border-radius: 10px; min-height: 0; }
  .preview { display: flex; align-items: center; gap: 5px; padding: 8px; border-radius: 6px; }
  .bar { width: 28px; height: 6px; border-radius: 3px; margin-right: auto; }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .nm { font-size: 13px; font-weight: 600; }
  .by { font-size: 11px; min-height: 14px; }
  .del { position: absolute; top: 4px; right: 8px; font-size: 16px; cursor: pointer; }
  details { margin-top: 8px; border-top: 1px solid var(--line); padding-top: 10px; }
  summary { cursor: pointer; font-weight: 600; }
  textarea { width: 100%; background: var(--bg); color: var(--ink); border: 1px solid var(--line-2); border-radius: 6px; padding: 8px; font: 12px var(--mono); margin: 8px 0; }
  .err { color: var(--warn); margin: 0 0 8px; font-size: 13px; }
  .muted { color: var(--muted); font-size: 13px; }
</style>
