<script lang="ts">
  import { onMount } from 'svelte'
  import { app } from './lib/state.svelte'
  import { theme } from './lib/theme.svelte'
  import Header from './lib/components/Header.svelte'
  import GraphPanel from './lib/components/GraphPanel.svelte'
  import Inspector from './lib/components/Inspector.svelte'
  import Strips from './lib/components/Strips.svelte'
  import OutputSelector from './lib/components/OutputSelector.svelte'
  import DriveView from './lib/components/DriveView.svelte'
  import SetupWizard from './lib/components/SetupWizard.svelte'
  import ProposalCard from './lib/components/ProposalCard.svelte'
  import SystemView from './lib/components/SystemView.svelte'
  import SessionGate from './lib/components/SessionGate.svelte'
  import MeasurementsView from './lib/components/MeasurementsView.svelte'

  onMount(() => {
    theme.apply()
  })
</script>

<SessionGate onlocked={() => app.stop()} onready={() => { theme.load(); app.start() }}>
<a class="skip-link" href="#workstation-content">Skip to workstation</a>
<Header />
<main id="workstation-content" tabindex="-1">
{#if app.mode === 'studio'}
  <div class="studio">
    <OutputSelector />
    <div class="area-graph"><GraphPanel /></div>
    <section class="area-inspector stack" id="output-inspector" aria-label="Output controls" tabindex="-1"><ProposalCard /><Inspector /></section>
    <div class="area-strips"><Strips /></div>
  </div>
{:else if app.mode === 'drive'}
  <DriveView />
{:else if app.mode === 'system'}
  <SystemView />
{:else if app.mode === 'measurements'}
  <MeasurementsView />
{:else}
  <SetupWizard />
{/if}

</main>
<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.id)}
    <div class="toast {t.kind}">{t.text}</div>
  {/each}
</div>
</SessionGate>

<style>
  .skip-link { position: fixed; top: 8px; left: 8px; transform: translateY(-200%); z-index: 100; padding: 12px; border-radius: 8px; color: var(--accent-ink); background: var(--accent); }
  .skip-link:focus { transform: translateY(0); }
  .stack { display: flex; flex-direction: column; gap: var(--gap); }
  .toasts { position: fixed; left: 16px; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 8px; align-items: center; z-index: 20; pointer-events: none; }
  .toast { max-width: 640px; padding: 10px 14px; border-radius: 10px; background: var(--toast-err-bg); color: var(--ink); border: 1px solid var(--warn); white-space: pre-wrap; font-size: 14px; }
  .toast.info { background: var(--toast-ok-bg); border-color: var(--ok); }
</style>
