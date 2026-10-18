<script lang="ts">
  import { app } from '../state.svelte'
  // Persistent, actionable notices shown in every view: refused changes and the reviewed
  // "Unmute at 0 dB" offer. Toasts disappear too quickly to read or act on.
  const fmt = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(1)} dB`
  const review = $derived(app.unmuteReview)
  const ids = $derived(review ? review.targets.map((t) => t.id).join(' + ') : '')
  // Nonmodal: the page stays usable. Escape cancels the review or dismisses the notice.
  function onkey(e: KeyboardEvent) {
    if (e.key !== 'Escape') return
    if (app.unmuteReview) app.unmuteReview = null
    else if (app.rejection) app.rejection = null
  }
</script>

<svelte:window onkeydown={onkey} />

{#if review}
  <section class="notice" aria-live="assertive" aria-labelledby="unmute-title">
    <h3 id="unmute-title">Unmute {ids} at 0 dB?</h3>
    <p>The level was raised while muted, or isn't known from before the mute, so a direct unmute could jump loudly.</p>
    <ul>
      {#each review.targets as t}
        <li><strong>{t.id}</strong> level {fmt(t.gain_db)} → {fmt(Math.min(t.gain_db, 0))}</li>
      {/each}
    </ul>
    <p class="muted">Raise the level again afterwards in steps of up to 3 dB.</p>
    <div class="actions">
      <button class="primary" disabled={app.busy} onclick={() => app.confirmUnmuteAtZero()}>Unmute at 0 dB</button>
      <button onclick={() => (app.unmuteReview = null)}>Keep muted (Esc)</button>
    </div>
  </section>
{:else if app.rejection}
  <section class="notice" aria-live="assertive" aria-labelledby="rejected-title">
    <h3 id="rejected-title">Not applied</h3>
    <p>Nothing was changed or sent to the DSP:</p>
    <ul>{#each app.rejection.reasons as reason}<li>{reason}</li>{/each}</ul>
    <div class="actions"><button onclick={() => (app.rejection = null)}>Dismiss (Esc)</button></div>
  </section>
{/if}

<style>
  .notice { position: fixed; right: 16px; bottom: 16px; z-index: 30; width: min(440px, calc(100vw - 32px)); box-sizing: border-box;
            padding: 14px 16px; background: var(--panel); color: var(--ink); border: 1px solid var(--caution);
            border-radius: var(--radius); box-shadow: 0 16px 48px rgb(0 0 0 / .35);
            max-height: min(60dvh, 480px); overflow-y: auto; }
  h3 { margin: 0 0 6px; font-size: 15px; }
  p { margin: 0 0 6px; font-size: 13px; }
  ul { margin: 0 0 8px; padding-left: 18px; font-size: 13px; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
