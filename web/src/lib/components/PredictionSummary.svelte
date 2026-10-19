<script lang="ts">
  import { app } from '../state.svelte'
  import { predictionSummary } from '../prediction'
  const view = $derived(app.system)
</script>

<div class="context">
  <p>{predictionSummary(view)}</p>
  {#if view}
    <details>
      <summary>{view.measurement_count} included · {view.excluded.length} excluded · assumptions and sources</summary>
      {#if view.measurement_count}<p>Target level follows the selected estimate around 300 Hz–3 kHz; it is not an independent SPL reference.</p>{/if}
      <ul>{#each view.limitations as limitation}<li>{limitation}</li>{/each}</ul>
      {#each view.contributors as contributor}
        <p><strong>{contributor.name}</strong> · {contributor.channels.join(', ')} · {contributor.frequency_range_hz.join('–')} Hz · {new Date(contributor.taken_at * 1000).toLocaleDateString()}</p>
      {/each}
      {#each view.excluded as excluded}
        <p><strong>Excluded: {excluded.name}</strong> · {excluded.reason}</p>
      {/each}
      {#if !view.measurement_count}<button onclick={() => app.mode = 'measurements'}>Review measurements</button>{/if}
    </details>
  {/if}
</div>

<style>
  .context { font-size: 12px; color: var(--muted); }
  p { margin: 4px 0; line-height: 1.4; overflow-wrap: anywhere; }
  summary { cursor: pointer; }
  details[open] { max-height: 200px; overflow-y: auto; padding: 8px; border: 1px solid var(--line); }
  ul { padding-left: 18px; }
</style>
