<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte'
  import type { Component } from '../types'
  import { KIND_LABEL } from '../types'
  import { mediaUrl } from './drag.svelte'

  let { data, selected }: { data: { c: Component; color: string }; selected?: boolean } = $props()
  const img = $derived(mediaUrl(data.c.image))
</script>

<div class="pin" class:sel={selected} style="--ring:{data.color}">
  {#if img}<img src={img} alt="" draggable="false" />{:else}<span class="ph" aria-hidden="true">{KIND_LABEL[data.c.kind][0]}</span>{/if}
  <span class="lbl">{data.c.name || data.c.model || KIND_LABEL[data.c.kind]}</span>
  <Handle type="source" position={Position.Top} id="c" isConnectable={false} class="hidden-h" />
  <Handle type="target" position={Position.Top} id="c" isConnectable={false} class="hidden-h" />
</div>

<style>
  .pin { display: flex; flex-direction: column; align-items: center; gap: 4px; width: 96px; }
  img, .ph { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; border: 3px solid var(--ring); background: var(--panel-2);
             box-shadow: 0 2px 6px rgb(0 0 0 / .45); }
  .ph { display: grid; place-items: center; color: var(--ink); font-weight: 600; }
  .sel img, .sel .ph { outline: 3px solid var(--accent); outline-offset: 2px; }
  .lbl { font: 600 11px var(--font); color: var(--ink); background: color-mix(in srgb, var(--panel) 85%, transparent);
         padding: 2px 6px; border-radius: 4px; max-width: 96px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  :global(.hidden-h) { opacity: 0; top: 26px !important; pointer-events: none; }
</style>
