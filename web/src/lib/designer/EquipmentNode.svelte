<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte'
  import type { Component } from '../types'
  import { KIND_LABEL, SIGNAL_STYLE } from '../types'
  import { handleId, type Port } from '../ports'
  import { drag, mediaUrl } from './drag.svelte'

  let { data, selected }: { data: { c: Component; ports: Port[]; color: string }; selected?: boolean } = $props()

  const HEAD = 64, ROW = 24
  const main = $derived(data.ports.filter((p) => p.group === 'main'))
  const ins = $derived(main.filter((p) => p.dir === 'in'))
  const outs = $derived(main.filter((p) => p.dir === 'out'))
  const pwr = $derived(data.ports.filter((p) => p.group === 'power'))
  const rows = $derived(Math.max(ins.length, outs.length))
  const img = $derived(mediaUrl(data.c.image))
  const sub = $derived([data.c.make, data.c.model].filter(Boolean).join(' '))

  // while a wire is being dragged, dim ports it can't plug into
  function state(p: Port): '' | 'ok' | 'no' {
    if (!drag.signal) return ''
    if (drag.fromNode === data.c.id) return 'no'
    const sigOk = p.signal === drag.signal || p.signal === 'other' || drag.signal === 'other'
    return sigOk && p.dir !== drag.fromDir ? 'ok' : 'no'
  }
</script>

<div class="node" class:sel={selected} style="--stripe:{data.color}; height:{HEAD + rows * ROW + (pwr.length ? 34 : 8)}px">
  <div class="head">
    {#if img}<img src={img} alt="" class="thumb" draggable="false" />{:else}<div class="thumb ph" aria-hidden="true">{KIND_LABEL[data.c.kind][0]}</div>{/if}
    <div class="txt">
      <div class="kind">{KIND_LABEL[data.c.kind].toUpperCase()}{data.c.channels.length ? ` · ${data.c.channels.join(',')}` : ''}</div>
      <div class="name">{data.c.name || sub || KIND_LABEL[data.c.kind]}</div>
      <div class="sub" class:missing={!sub}>{sub || 'model not recorded'}</div>
    </div>
  </div>
  {#each ins as p, i (p.id)}
    <span class="plabel in {state(p)}" style="top:{HEAD + i * ROW}px">{p.label}</span>
    <Handle type="target" position={Position.Left} id={handleId(p)} class="port {state(p)}"
            style="top:{HEAD + i * ROW + ROW / 2}px; --pc:{SIGNAL_STYLE[p.signal].color}" />
  {/each}
  {#each outs as p, i (p.id)}
    <span class="plabel out {state(p)}" style="top:{HEAD + i * ROW}px">{p.label}</span>
    <Handle type="source" position={Position.Right} id={handleId(p)} class="port {state(p)}"
            style="top:{HEAD + i * ROW + ROW / 2}px; --pc:{SIGNAL_STYLE[p.signal].color}" />
  {/each}
  {#if pwr.length}
    <div class="pwr">
      {#each pwr as p, i (p.id)}
        <span class="plabel pw {state(p)}" style="left:{((i + 0.5) / pwr.length) * 100}%">{p.label}</span>
        <Handle type={p.dir === 'out' ? 'source' : 'target'} position={Position.Bottom} id={handleId(p)} class="port {state(p)}"
                style="left:{((i + 0.5) / pwr.length) * 100}%; --pc:{SIGNAL_STYLE[p.signal].color}" />
      {/each}
    </div>
  {/if}
</div>

<style>
  .node { width: 250px; background: var(--panel-2); border: 1px solid var(--line-2); border-radius: 10px; position: relative;
          box-shadow: 0 1px 0 rgb(0 0 0 / .2); color: var(--ink); font-family: var(--font); }
  .node::before { content: ''; position: absolute; left: 0; top: 8px; bottom: 8px; width: 3px; border-radius: 2px; background: var(--stripe); }
  .node.sel { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent); }
  .head { display: flex; gap: 10px; padding: 8px 10px 0 12px; height: 56px; }
  .thumb { width: 44px; height: 44px; border-radius: 8px; object-fit: cover; flex: none; background: var(--bg); }
  .ph { display: grid; place-items: center; color: var(--muted); font-weight: 600; border: 1px dashed var(--line-2); }
  .txt { min-width: 0; }
  .kind { font: 600 10px var(--font); letter-spacing: .08em; color: var(--muted); }
  .name { font: 600 14px var(--font); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 170px; }
  .sub { font: 11px var(--mono); color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 170px; }
  .sub.missing { color: var(--dim); font-style: italic; }
  .plabel { position: absolute; font: 11px var(--mono); color: var(--muted); line-height: 24px; white-space: nowrap; pointer-events: none;
            max-width: 112px; overflow: hidden; text-overflow: ellipsis; }
  .plabel.in { left: 12px; }
  .plabel.out { right: 12px; text-align: right; }
  .plabel.no { opacity: .3; }
  .plabel.ok { color: var(--ink); }
  .pwr { position: absolute; left: 0; right: 0; bottom: 0; height: 30px; border-top: 1px dashed var(--line-2); }
  .plabel.pw { bottom: 4px; transform: translateX(-50%); font-size: 10px; line-height: 14px; }
  :global(.svelte-flow__handle.port) { width: 12px; height: 12px; background: var(--pc); border: 2px solid var(--panel-2); transition: transform .12s, opacity .12s; }
  :global(.svelte-flow__handle.port.no) { opacity: .2; }
  :global(.svelte-flow__handle.port.ok) { transform: translate(-50%, -50%) scale(1.45); box-shadow: 0 0 0 3px color-mix(in srgb, var(--pc) 40%, transparent); }
  :global(.svelte-flow__handle-bottom.port.ok) { transform: translate(-50%, 50%) scale(1.45); }
  :global(.svelte-flow__handle-right.port.ok) { transform: translate(50%, -50%) scale(1.45); }
</style>
