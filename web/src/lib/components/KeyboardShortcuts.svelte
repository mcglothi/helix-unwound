<script lang="ts">
  import { app } from '../state.svelte'
  import { adjacentOutput, shortcutFor } from '../shortcuts'
  let dialog: HTMLDialogElement
  function keydown(event: KeyboardEvent) {
    if (!app.tune || event.defaultPrevented || event.isComposing) return
    const editable = event.composedPath().some(target => target instanceof HTMLElement &&
      (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable))
    const action = shortcutFor(event, editable, !!document.querySelector('dialog[open]'))
    if (!action || app.busy) return
    if (action === 'help') { event.preventDefault(); dialog.showModal(); return }
    if (action === 'undo' && app.status?.undo_depth) { event.preventDefault(); void app.undo() }
    if (action === 'redo' && app.status?.redo_depth) { event.preventDefault(); void app.redo() }
    if (app.mode === 'studio' && (action === 'previous-output' || action === 'next-output')) {
      event.preventDefault()
      const ids = app.tune.channels.map(c => c.id).sort()
      app.selected = adjacentOutput(ids, app.selected, action === 'previous-output' ? -1 : 1)
    }
  }
</script>

<svelte:window onkeydown={keydown} />
<button aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" onclick={() => dialog.showModal()}>Keys</button>
<dialog bind:this={dialog} aria-labelledby="keys-title">
  <h2 id="keys-title">Keyboard shortcuts</h2>
  <dl>
    <div><dt>Undo tuning change</dt><dd>⌘ / Ctrl + Z</dd></div>
    <div><dt>Redo tuning change</dt><dd>⌘ / Ctrl + Shift + Z<br />Ctrl + Y</dd></div>
    <div><dt>Previous / next output in Studio</dt><dd>[ / ]</dd></div>
    <div><dt>Show this help</dt><dd>?</dd></div>
    <div><dt>Close a dialog</dt><dd>Esc</dd></div>
  </dl>
  <p>Shortcuts pause while typing or while a dialog is open. Use Tab to reach controls and Enter or Space to activate buttons.</p>
  <button onclick={() => dialog.close()}>Close</button>
</dialog>
<style>
  dialog { width: min(460px, calc(100vw - 24px)); max-height: 85dvh; overflow-y: auto; box-sizing: border-box; background: var(--panel); color: var(--ink); border: 1px solid var(--line-2); border-radius: var(--radius); padding: 22px; }
  dialog::backdrop { background: rgb(0 0 0 / .55); }
  h2 { margin-top: 0; font-size: 20px; }
  dl { display: grid; gap: 14px; }
  dl > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
  dt, p { font-size: 13px; line-height: 1.5; }
  dd { font: 13px var(--mono); margin: 0; }
  p { color: var(--muted); }
</style>
