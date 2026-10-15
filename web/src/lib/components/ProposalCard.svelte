<script lang="ts">
  import { app } from '../state.svelte'

  const p = $derived(app.proposal)
  const fromAgent = $derived(p?.source === 'agent')
</script>

{#if p}
  <section class="card panel" aria-label="Proposed changes">
    <header>
      <div>
        <div class="kicker">{fromAgent ? 'Proposed by agent' : 'Proposed'} · {p.edits.length} change{p.edits.length === 1 ? '' : 's'}</div>
        <h2>{p.title}</h2>
      </div>
      <span class="legend"><span class="sw"></span>after (on graph)</span>
    </header>
    {#if p.edits.length}
      <ul>
        {#each p.edits as e}<li class="mono">{e.label}</li>{/each}
      </ul>
    {/if}
    {#each p.notes as n}<p class="note">{n}</p>{/each}
    {#if app.proposalConflicts.length}
      <div class="conflict" role="alert">
        <b>Out of date — recompute this proposal.</b>
        <ul>{#each app.proposalConflicts as c}<li>{c}</li>{/each}</ul>
      </div>
    {/if}
    <div class="actions">
      <button class="ghost" onclick={() => app.discardProposal()}>Discard</button>
      <button class="primary" disabled={!p.edits.length || app.proposalConflicts.length > 0} onclick={() => app.applyProposal()}>
        Apply{app.status?.device.writes_enabled && app.status?.device.baselined ? ' to DSP' : ''}
      </button>
    </div>
    <p class="fine muted">Safety limits are checked on apply. Undo reverts it in one step.</p>
  </section>
{/if}

<style>
  .card { padding: 14px 16px; border-color: var(--accent); display: flex; flex-direction: column; gap: 10px; }
  header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .kicker { color: var(--accent-text); font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
  h2 { margin: 2px 0 0; font-size: 17px; }
  .legend { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); white-space: nowrap; }
  .sw { width: 18px; border-top: 3px dashed var(--accent); }
  ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 4px; font-size: 12px; max-height: 220px; overflow: auto; }
  .note { margin: 0; font-size: 13px; color: var(--muted); }
  .actions { display: flex; gap: 8px; justify-content: flex-end; }
  .fine { font-size: 12px; margin: 0; }
  .conflict { border: 1px solid var(--warn); border-radius: 8px; padding: 8px 10px; font-size: 13px; }
  .conflict b { color: var(--warn); }
  .conflict ul { margin: 4px 0 0; padding-left: 18px; }
</style>
