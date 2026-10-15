<script lang="ts">
  import { onMount } from 'svelte'
  import { app } from './lib/state.svelte'
  import { theme } from './lib/theme.svelte'
  import Header from './lib/components/Header.svelte'
  import GraphPanel from './lib/components/GraphPanel.svelte'
  import Inspector from './lib/components/Inspector.svelte'
  import Strips from './lib/components/Strips.svelte'
  import DriveView from './lib/components/DriveView.svelte'
  import SetupWizard from './lib/components/SetupWizard.svelte'
  import ProposalCard from './lib/components/ProposalCard.svelte'
  import SystemView from './lib/components/SystemView.svelte'

  onMount(() => {
    theme.load()
    app.start()
  })
</script>

<Header />
{#if app.mode === 'studio'}
  <div class="studio">
    <div class="area-graph"><GraphPanel /></div>
    <div class="area-inspector stack"><ProposalCard /><Inspector /></div>
    <div class="area-strips"><Strips /></div>
  </div>
{:else if app.mode === 'drive'}
  <DriveView />
{:else if app.mode === 'system'}
  <SystemView />
{:else}
  <SetupWizard />
{/if}

<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.id)}
    <div class="toast {t.kind}">{t.text}</div>
  {/each}
</div>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--gap); }
  .toasts { position: fixed; left: 16px; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 8px; align-items: center; z-index: 20; pointer-events: none; }
  .toast { max-width: 640px; padding: 10px 14px; border-radius: 10px; background: var(--toast-err-bg); color: var(--ink); border: 1px solid var(--warn); white-space: pre-wrap; font-size: 14px; }
  .toast.info { background: var(--toast-ok-bg); border-color: var(--ok); }
</style>
