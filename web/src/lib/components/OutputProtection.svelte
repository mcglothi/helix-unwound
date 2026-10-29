<script lang="ts">
  import { app } from '../state.svelte'
  import ConstraintReview from './ProtectionConstraint.svelte'
  let { cid }: { cid: string } = $props()
  const guard = $derived(app.protections[cid])
  const margin = $derived(app.advisoryProtections[cid]?.min_hp_hz ?? null)
  const connected = $derived(!!app.status && app.status.device.kind !== 'none')
  const items = $derived(Object.values(app.protectionConstraints).filter(item => item.output === cid))
  const pending = $derived(items.filter(item => item.state === 'pending').length)
</script>

{#if guard}
  <details class="protection">
    <summary>Output {cid} limits · {guard.min_hp_hz ? `HP ≥ ${guard.min_hp_hz} Hz` : 'no HP minimum'}{margin && margin > (guard.min_hp_hz ?? 0) ? ` (recommended ≥ ${margin} Hz)` : ''} · {pending} pending</summary>
    <p class="muted">Pending and owner-confirmed constraints both enforce immediately and persist across scenes, restarts, and source removal. Source text never grants confirmation.</p>
    <p>Effective: HP {guard.min_hp_hz ?? 'none'} Hz · slope {guard.min_hp_slope_db} dB/oct · LP {guard.max_lp_hz ?? 'none'} Hz · Fs multiplier {guard.fs_factor}</p>
    {#if connected}<p>Disconnect before clearing a limit. Software disconnect does not silence the DSP.</p>{/if}
    {#each items as item (item.id)}
      <ConstraintReview {item} {connected} />
    {:else}
      <p class="muted">No recorded constraints for this output.</p>
    {/each}
  </details>
{/if}

<style>
  .protection { padding: 12px 0; border-top: 1px solid var(--line); }
  summary { cursor: pointer; font-size: 13px; }
  p { font-size: 12px; line-height: 1.5; }
</style>
