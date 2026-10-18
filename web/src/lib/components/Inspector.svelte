<script lang="ts">
  import { app } from '../state.svelte'
  import type { Crossover, EqType, Role, XoType } from '../types'
  import { ROLE_COLORS, ROLE_LABEL, SOURCE_LABEL, SOURCE_MIX, sourceOf } from '../types'
  import { fmtHz } from '../dsp'
  import OutputProtection from './OutputProtection.svelte'

  const ch = $derived(app.channel)
  const partners = $derived(ch && ch.link_group
    ? (app.tune?.channels ?? []).filter((o) => o.link_group === ch.link_group && o.id !== ch.id).map((o) => o.id) : [])
  const ROLES: Role[] = ['tweeter', 'midrange', 'midbass', 'woofer', 'subwoofer', 'fullrange', 'unused']
  const EQT: EqType[] = ['peak', 'low_shelf', 'high_shelf', 'notch', 'allpass']
  const XOT: { v: XoType; l: string }[] = [
    { v: 'linkwitz_riley', l: 'Linkwitz-Riley' }, { v: 'butterworth', l: 'Butterworth' }, { v: 'bessel', l: 'Bessel' },
  ]
  const SLOPES = [6, 12, 18, 24, 30, 36, 42, 48]
  const SPEED_OF_SOUND = 343 // m/s at ~20 °C

  let showAll = $state(false)
  const rows = $derived(ch ? ch.eq.map((b, i) => ({ ...b, n: i + 1 })).filter((b) => showAll || b.enabled) : [])
  const used = $derived(ch ? ch.eq.filter((b) => b.enabled).length : 0)

  function xo(which: 'hp' | 'lp', patch: Partial<Crossover> | null) {
    if (!ch) return
    const cur = ch[which] ?? { type: 'linkwitz_riley', slope_db: 24, freq_hz: which === 'hp' ? 80 : 3000 }
    app.setCrossover(ch.id, which, patch === null ? null : { ...cur, ...patch })
  }
  const cm = (ms: number) => ((ms / 1000) * SPEED_OF_SOUND * 100).toFixed(1)
</script>

{#if ch}
  <section class="panel inspector">
    <header>
      <span class="swatch" style="background:{ROLE_COLORS[ch.role]}"></span>
      <input class="name" value={ch.name} placeholder="Channel {ch.id}" aria-label="Channel name"
             onchange={(e) => app.patchChannel(ch.id, { name: e.currentTarget.value })} />
      <span class="mono muted">Out {ch.id}</span>
    </header>
    {#each (app.status?.advisories ?? []).filter((a) => a.startsWith(`${ch.id}:`)) as note}
      <p class="advisory" role="status">⚠ {note.slice(ch.id.length + 2)}</p>
    {/each}
    {#if partners.length}
      <p class="linknote muted">Linked with {partners.join(', ')}: gain, mute, polarity, crossover and EQ edits apply to
        {partners.length > 1 ? 'all of them' : 'both'} (delay, name and routing stay separate).
        <button class="link" onclick={() => app.patchChannel(ch.id, { link_group: 0 })}>Unlink {ch.id}</button></p>
    {/if}

    <div class="row2">
      <label>Role label
        <select value={ch.role} onchange={(e) => app.patchChannel(ch.id, { role: e.currentTarget.value as Role })}>
          {#each ROLES as r}<option value={r}>{ROLE_LABEL[r]}</option>{/each}
        </select>
      </label>
      <label>Level (dB)
        <input type="number" step="0.5" value={ch.gain_db} onchange={(e) => app.patchChannel(ch.id, { gain_db: +e.currentTarget.value })} />
      </label>
      <label>Delay (ms)
        <input type="number" step="0.01" min="0" value={ch.delay_ms} onchange={(e) => app.patchChannel(ch.id, { delay_ms: +e.currentTarget.value })} />
      </label>
      <label>Distance (cm)
        <input type="number" step="0.5" min="0" value={cm(ch.delay_ms)}
               onchange={(e) => app.patchChannel(ch.id, { delay_ms: +(((+e.currentTarget.value / 100) / SPEED_OF_SOUND) * 1000).toFixed(4) })} />
      </label>
    </div>
    <OutputProtection cid={ch.id} />
    <div class="src">
      <span class="lbl">Input</span>
      <div class="seg" role="group" aria-label="Input source">
        {#each (['L', 'R', 'mono', 'off'] as const) as k}
          <button class:active={sourceOf(ch.mix) === k} aria-pressed={sourceOf(ch.mix) === k}
                  onclick={() => app.patchChannel(ch.id, { mix: SOURCE_MIX[k] })}>{SOURCE_LABEL[k]}</button>
        {/each}
      </div>
    </div>
    <div class="toggles">
      <button class:on={ch.mute} aria-pressed={ch.mute} onclick={() => app.patchChannel(ch.id, { mute: !ch.mute })}>Mute</button>
      <button class:on={ch.invert} aria-pressed={ch.invert} onclick={() => app.patchChannel(ch.id, { invert: !ch.invert })}>Invert polarity</button>
    </div>

    {#each [['hp', 'High-pass'], ['lp', 'Low-pass']] as [which, label]}
      {@const x = ch[which as 'hp' | 'lp']}
      <div class="xo">
        <label class="inline"><input type="checkbox" checked={!!x} onchange={(e) => xo(which as 'hp' | 'lp', e.currentTarget.checked ? {} : null)} /> {label}</label>
        {#if x}
          <div class="row3">
            <label title="Where the filter starts working, in hertz">Frequency (Hz)
              <input type="number" min="10" max="24000" value={x.freq_hz} aria-label="{label} frequency (Hz)"
                     onchange={(e) => xo(which as 'hp' | 'lp', { freq_hz: +e.currentTarget.value })} /></label>
            <label title="How steeply it rolls off past the frequency: decibels per octave. Higher = steeper">Slope
              <select value={x.slope_db} aria-label="{label} slope" onchange={(e) => xo(which as 'hp' | 'lp', { slope_db: +e.currentTarget.value })}>
                {#each SLOPES as s}<option value={s}>{s} dB/oct</option>{/each}
              </select></label>
            <label title="Filter shape. Linkwitz-Riley is the usual crossover choice: it blends flat with the matching filter on the neighbouring speaker">Type
              <select value={x.type} aria-label="{label} type" onchange={(e) => xo(which as 'hp' | 'lp', { type: e.currentTarget.value as XoType })}>
                {#each XOT as t}<option value={t.v}>{t.l}</option>{/each}
              </select></label>
          </div>
        {/if}
      </div>
    {/each}

    <div class="eqhead">
      <span class="label">EQ · {used} of 30 bands</span>
      <button class="ghost small" onclick={() => (showAll = !showAll)}>{showAll ? 'Active only' : 'All 30'}</button>
    </div>
    <p class="hint muted">Drag points on the graph · scroll for Q · double-click empty space to add</p>
    <div class="bands">
      {#if rows.length}
        <div class="band colhead" aria-hidden="true">
          <span title="Tick to switch the band on; the number is the band (1-30)">On · #</span>
          <span title="Filter shape: peak boosts or cuts around one frequency; shelves lift or lower everything above/below it">Type</span>
          <span title="Center frequency of the band, in hertz">Freq (Hz)</span>
          <span title="Boost (+) or cut (−) in decibels">Gain (dB)</span>
          <span title="Width of the band: higher Q = narrower, lower Q = wider">Q (width)</span>
        </div>
      {/if}
      {#each rows as b (b.n)}
        <div class="band" class:off={!b.enabled}>
          <label class="inline n"><input type="checkbox" checked={b.enabled} aria-label="Band {b.n} on"
                 onchange={(e) => app.patchBand(ch.id, b.n, { enabled: e.currentTarget.checked })} />{b.n}</label>
          <select value={b.type} aria-label="Band {b.n} type" title="Filter shape" onchange={(e) => app.patchBand(ch.id, b.n, { type: e.currentTarget.value as EqType })}>
            {#each EQT as t}<option value={t}>{t.replace('_', ' ')}</option>{/each}
          </select>
          <input type="number" value={Math.round(b.freq_hz)} aria-label="Band {b.n} frequency (Hz)" title="Center frequency: {fmtHz(b.freq_hz)} Hz"
                 onchange={(e) => app.patchBand(ch.id, b.n, { freq_hz: +e.currentTarget.value })} />
          <input type="number" step="0.25" value={b.gain_db} aria-label="Band {b.n} gain (dB)" title="Boost (+) or cut (−) in dB"
                 onchange={(e) => app.patchBand(ch.id, b.n, { gain_db: +e.currentTarget.value })} />
          <input type="number" step="0.1" min="0.1" value={b.q} aria-label="Band {b.n} Q (width)" title="Q = width: higher is narrower"
                 onchange={(e) => app.patchBand(ch.id, b.n, { q: +e.currentTarget.value })} />
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .inspector { padding: 14px; display: flex; flex-direction: column; gap: 12px; height: 100%; overflow: auto; }
  header { display: flex; align-items: center; gap: 10px; }
  .linknote { margin: 6px 0 0; font-size: 12px; }
  .advisory { margin: 6px 0 0; font-size: 12px; color: var(--caution); }
  .linknote .link { padding: 2px 8px; font-size: 12px; margin-left: 6px; }
  .swatch { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .name { flex: 1; min-width: 0; font-weight: 600; font-size: 16px; background: transparent; border-color: transparent; }
  .name:hover, .name:focus { border-color: var(--line-2); }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  label.inline { flex-direction: row; align-items: center; gap: 8px; color: var(--ink); font-size: 14px; }
  .row2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .row3 { display: grid; grid-template-columns: 1fr 1.1fr 1.4fr; gap: 6px; margin-top: 6px; }
  .toggles { display: flex; gap: 8px; }
  .src { display: flex; flex-direction: column; gap: 4px; }
  .src .lbl { font-size: 12px; color: var(--muted); }
  .seg { display: flex; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
  .seg button { flex: 1; border: 0; background: transparent; color: var(--muted); min-height: 30px; font-size: 12px; padding: 0 4px; }
  .seg button.active { background: var(--panel-2); color: var(--ink); box-shadow: inset 0 -2px 0 var(--accent); }
  .toggles button { flex: 1; }
  .xo { border-top: 1px solid var(--line); padding-top: 10px; }
  .eqhead { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--line); padding-top: 10px; }
  .small { min-height: 28px; font-size: 12px; }
  .hint { font-size: 12px; margin: -6px 0 0; }
  .bands { display: flex; flex-direction: column; }
  .band { display: grid; grid-template-columns: 48px 1.2fr 1fr 0.8fr 0.7fr; gap: 4px; padding: 3px 0; align-items: center; }
  .band.off { opacity: .5; }
  .colhead { padding: 0 0 2px; font-size: 11px; color: var(--muted); border-bottom: 1px solid var(--line); }
  .colhead span { cursor: help; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .band input, .band select { min-height: 30px; font-size: 12px; padding: 0 4px; }
  .n { font-family: var(--mono); font-size: 12px !important; }
</style>
