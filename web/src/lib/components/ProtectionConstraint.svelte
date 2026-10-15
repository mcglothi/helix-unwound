<script lang="ts">
  import { app } from '../state.svelte'
  import type { ProtectionConstraint } from '../types'
  import { constraintLabel, canReviewConstraint } from '../protections'
  let { item, connected }: { item: ProtectionConstraint; connected: boolean } = $props()
  let reason = $state('')
  const rights = $derived(canReviewConstraint(item, connected, reason))
  function review(action: 'confirm' | 'clear') {
    if (!rights[action]) return
    if (!confirm(`${action === 'clear' ? 'Clear' : 'Confirm'} ${constraintLabel(item)} on output ${item.output}? ${action === 'clear' ? 'This may weaken the enforced limits. Software disconnect does not silence the DSP.' : 'Verify the exact source and installed driver assignment below.'}`)) return
    app.reviewProtection(item, action, reason)
  }
</script>

<article>
  <strong>{constraintLabel(item)}</strong>
  <p>{item.state === 'pending' ? 'Pending owner review · enforced' : item.state === 'confirmed' ? 'Owner confirmed · enforced' : 'Cleared · retained in history'}</p>
  <p class="muted">{item.current ? 'Source matches current metadata' : 'Source changed or removed · retained independently'}</p>
  <details>
    <summary>Exact source and review history</summary>
    <pre>{JSON.stringify(item.source, null, 2)}</pre>
    <p class="muted">Revision {item.id}</p>
    {#each item.history as review}
      <p>{new Date(review.at * 1000).toLocaleString()} · {review.actor} · {review.action}: {review.reason}</p>
    {/each}
  </details>
  {#if item.state !== 'cleared'}
    <label>Evidence / reason<textarea bind:value={reason} maxlength="2000" placeholder="Datasheet reference, physical wiring check, or reason for clearing"></textarea></label>
    <div class="actions">
      <button disabled={!rights.confirm || app.busy} onclick={() => review('confirm')}>Confirm exact source</button>
      <button disabled={!rights.clear || app.busy} onclick={() => review('clear')}>Clear retained limit…</button>
    </div>
    {#if item.current}<p class="muted">To clear, correct or remove its role/specification first.</p>{/if}
  {/if}
</article>

<style>
  article { padding: 12px 0; border-bottom: 1px solid var(--line); font-size: 12px; }
  p { margin: 6px 0; overflow-wrap: anywhere; }
  pre { font-size: 11px; white-space: pre-wrap; overflow-wrap: anywhere; }
  summary { cursor: pointer; }
  label { display: grid; gap: 4px; margin: 10px 0; }
  textarea { min-height: 60px; width: 100%; box-sizing: border-box; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
