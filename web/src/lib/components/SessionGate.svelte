<script lang="ts">
  import { onMount, type Snippet } from 'svelte'
  import { consumeBootstrap, unlockSession, SESSION_ENDED } from '../session'

  let { children, onready, onlocked }: { children: Snippet; onready: () => void; onlocked: () => void } = $props()
  let ready = $state(false)
  let checking = $state(true)
  let token = $state('')
  let error = $state('')

  function start() {
    if (ready) return
    ready = true
    onready()
  }

  onMount(() => {
    function ended() {
      if (!ready) return
      ready = false
      checking = false
      error = 'Your browser session ended. Sign in again to continue.'
      onlocked()
    }
    window.addEventListener(SESSION_ENDED, ended)
    const initial = consumeBootstrap(location, (url) => history.replaceState(null, '', url))
    void (async () => {
      try {
        if (initial) await unlockSession(initial)
        if ((await fetch('/api/status')).ok) start()
      } catch {
        error = 'Could not unlock the workstation. Check that the engine is running.'
      } finally { checking = false }
    })()
    return () => window.removeEventListener(SESSION_ENDED, ended)
  })

  async function submit(event: SubmitEvent) {
    event.preventDefault()
    checking = true
    error = ''
    try {
      await unlockSession(token)
      token = ''
      start()
    } catch { error = 'Could not unlock the workstation. Check the engine and owner credential.' }
    finally { checking = false }
  }
</script>

{#if ready}
  {@render children()}
{:else}
  <main class="access panel">
    <h1>Helix Unwound</h1>
    <p>Open this workstation from the engine computer with <code>helixtune open</code>.</p>
    <p class="muted">You can also enter its owner credential below. Agent credentials work through MCP and the API.</p>
    <form onsubmit={submit}>
      <label>Owner credential<input type="password" autocomplete="off" bind:value={token} required /></label>
      <button class="primary" disabled={checking}>{checking ? 'Connecting…' : 'Open workstation'}</button>
    </form>
    {#if error}<p role="alert">{error}</p>{/if}
  </main>
{/if}

<style>
  .access { max-width: 520px; margin: 12vh auto; padding: 28px; }
  h1 { margin-top: 0; }
  p { line-height: 1.5; }
  form, label { display: flex; flex-direction: column; gap: 12px; }
</style>
