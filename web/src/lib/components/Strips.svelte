<script lang="ts">
  import { app } from '../state.svelte'
  import { ROLE_COLORS, sourceOf } from '../types'
  import { fmtHz } from '../dsp'

  const SRC_SHORT = { L: 'L', R: 'R', mono: 'L+R', off: 'off', custom: 'mix' } as const
  // PC-Tool link group: other channels that receive this channel's edits
  const linkedWith = (c: { id: string; link_group: number }) =>
    c.link_group ? (app.tune?.channels ?? []).filter((o) => o.link_group === c.link_group && o.id !== c.id).map((o) => o.id) : []

  const ORDER = ['subwoofer', 'woofer', 'midbass', 'midrange', 'tweeter', 'fullrange', 'unused']
  const chans = $derived(
    (app.tune?.channels ?? []).slice().sort((a, b) => ORDER.indexOf(a.role) - ORDER.indexOf(b.role) || a.id.localeCompare(b.id)),
  )
  // fader position: -24 dB at bottom .. +6 at top
  const pos = (db: number) => `${Math.max(0, Math.min(100, ((db + 24) / 30) * 100))}%`
  const xoText = (hp: any, lp: any) => (hp || lp ? `${hp ? fmtHz(hp.freq_hz) : ''}–${lp ? fmtHz(lp.freq_hz) : ''}` : 'full')
</script>

<div class="strips" role="list" aria-label="Output channels">
  {#each chans as c (c.id)}
    <div role="listitem" class="strip panel" class:sel={c.id === app.selected} class:unused={c.role === 'unused'}>
      <button class="head" onclick={() => (app.selected = c.id)} aria-label="Select channel {c.id}">
        <span class="bar" style="background:{ROLE_COLORS[c.role]}"></span>
        <span class="title"><b>{c.id}</b> {c.name || c.role} <span class="srcbadge">{SRC_SHORT[sourceOf(c.mix)]}</span>{#if linkedWith(c).length}<span class="srcbadge" title="Linked with {linkedWith(c).join(', ')}: gain, mute, polarity, crossovers and EQ edits apply to both">⛓ {linkedWith(c).join('')}</span>{/if}</span>
      </button>
      <div class="body">
        <div class="fader" aria-hidden="true"><div class="cap" style="bottom:{pos(c.gain_db)}"></div></div>
        <div class="vals mono">
          <span>{c.gain_db > 0 ? '+' : ''}{c.gain_db.toFixed(1)} dB</span>
          <span>{c.delay_ms.toFixed(2)} ms</span>
          <span>{xoText(c.hp, c.lp)}</span>
        </div>
      </div>
      <div class="btns">
        <button class:on={c.mute} aria-pressed={c.mute} aria-label="Mute {c.id}" onclick={() => app.toggleMute(c.id)}>M</button>
        <button class:on={c.invert} aria-pressed={c.invert} aria-label="Invert {c.id}" onclick={() => app.patchChannel(c.id, { invert: !c.invert })}>Ø</button>
      </div>
    </div>
  {/each}
</div>

<style>
  .strips { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; scroll-snap-type: x proximity; }
  .strip { flex: 0 0 136px; padding: 8px; display: flex; flex-direction: column; gap: 8px; scroll-snap-align: start; }
  .strip.sel { border-color: var(--accent); }
  .strip.unused { opacity: .55; }
  .head { all: unset; cursor: pointer; display: flex; flex-direction: column; gap: 6px; border-radius: 6px; }
  .head:focus-visible { outline: 2px solid var(--accent); }
  .bar { height: 3px; border-radius: 2px; }
  .srcbadge { font: 10px var(--mono); color: var(--muted); border: 1px solid var(--line-2); border-radius: 4px; padding: 0 4px; margin-left: 2px; }
  .title { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .body { display: flex; gap: 12px; height: 64px; }
  .fader { width: 8px; height: 100%; background: var(--panel-2); border-radius: 4px; position: relative; margin-left: 6px; }
  .cap { position: absolute; left: -6px; width: 20px; height: 8px; border-radius: 3px; background: var(--ink); transform: translateY(50%); }
  .vals { display: flex; flex-direction: column; justify-content: space-between; font-size: 11px; color: var(--muted); }
  .btns { display: flex; gap: 4px; }
  .btns button { flex: 1; min-height: 30px; font-size: 12px; padding: 0; }
</style>
