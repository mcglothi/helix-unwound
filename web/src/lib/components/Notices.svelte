<script lang="ts">
  import { app } from '../state.svelte'
  // Persistent, actionable notices shown in every view: refused changes and the reviewed
  // "Unmute at 0 dB" offer. Toasts disappear too quickly to read or act on.
  const fmt = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(1)} dB`
  const review = $derived(app.unmuteReview)
  const ids = $derived(review ? review.targets.map((t) => t.id).join(' + ') : '')
</script>

{#if review}
  <div class="notice" role="alertdialog" aria-labelledby="unmute-title">
    <h3 id="unmute-title">Unmute {ids} at 0 dB?</h3>
    <p>Outputs with positive gain can't be unmuted directly, to avoid a sudden loud jump.</p>
    <ul>
      {#each review.targets as t}
        <li><strong>{t.id}</strong> level {fmt(t.gain_db)} → {fmt(Math.min(t.gain_db, 0))}</li>
      {/each}
    </ul>
    <p class="muted">Raise the level again afterwards in steps of up to 3 dB.</p>
    <div class="actions">
      <button class="primary" disabled={app.busy} onclick={() => app.confirmUnmuteAtZero()}>Unmute at 0 dB</button>
      <button onclick={() => (app.unmuteReview = null)}>Keep muted</button>
    </div>
  </div>
{:else if app.rejection}
  <section class="notice" role="alert">
    <h3>Not applied</h3>
    <p>Nothing was changed or sent to the DSP:</p>
    <ul>{#each app.rejection.reasons as reason}<li>{reason}</li>{/each}</ul>
    <div class="actions"><button onclick={() => (app.rejection = null)}>Dismiss</button></div>
  </section>
{/if}

<style>
  .notice { position: fixed; right: 16px; bottom: 16px; z-index: 30; width: min(440px, calc(100vw - 32px)); box-sizing: border-box;
            padding: 14px 16px; background: var(--panel); color: var(--ink); border: 1px solid var(--caution);
            border-radius: var(--radius); box-shadow: 0 16px 48px rgb(0 0 0 / .35); }
  h3 { margin: 0 0 6px; font-size: 15px; }
  p { margin: 0 0 6px; font-size: 13px; }
  ul { margin: 0 0 8px; padding-left: 18px; font-size: 13px; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
