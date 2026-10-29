<script lang="ts">
  import { app } from '../state.svelte'
  import { ROLE_LABEL } from '../types'
</script>
<div class="output-selector panel">
  <label for="studio-output">Output</label>
  <select id="studio-output" bind:value={app.selected}>
    {#each (app.tune?.channels ?? []).slice().sort((a, b) => a.id.localeCompare(b.id)) as channel}<option value={channel.id}>{channel.id} · {channel.name || ROLE_LABEL[channel.role]}</option>{/each}
  </select>
  <span class="muted" aria-live="polite">Editing {app.selected}</span>
  <a href="#output-inspector">Jump to controls</a>
</div>
<style>
  .output-selector { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 12px; min-width: 0; font-size: 13px; }
  select { flex: 1; min-width: 0; max-width: 420px; }
  @media (max-width: 700px) { select { flex-basis: calc(100% - 70px); max-width: none; } a { margin-left: auto; } }
  a { color: var(--accent-text); padding: 8px 0; }
</style>
