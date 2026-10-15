<script lang="ts">
  import { app } from '../state.svelte'
  import type { Channel, Role } from '../types'
  import { ROLE_COLORS, ROLE_LABEL } from '../types'
  import { fmtHz } from '../dsp'
  import Graph from './Graph.svelte'
  import ProposalCard from './ProposalCard.svelte'

  const STEPS = [
    { t: 'System', s: 'drivers, roles, safety' },
    { t: 'Levels', s: 'match driver output' },
    { t: 'Time alignment', s: 'distances to your head' },
    { t: 'Crossovers', s: 'points, slopes, overlap' },
    { t: 'EQ to target', s: 'auto-tune, review' },
    { t: 'Listen & A/B', s: 'compare, keep the best' },
  ]
  let step = $state(0)
  const chans = $derived(app.tune?.channels ?? [])
  const used = $derived(chans.filter((c) => c.role !== 'unused'))
  const hasMeas = $derived(!!app.system?.measurement_count)

  // ---- time alignment: distances (cm), seeded from current delays relative to the farthest driver
  let dist = $state<Record<string, number>>({})
  let distUnit = $state<'cm' | 'in'>('cm')
  function propose() {
    const cm = Object.fromEntries(Object.entries(dist).filter(([, v]) => v > 0).map(([k, v]) => [k, distUnit === 'in' ? v * 2.54 : v]))
    if (Object.keys(cm).length < 2) return app.toast('Enter distances for at least two speakers')
    app.proposeAlignment(cm)
  }

  // ---- crossover overlap check between adjacent driver groups
  const ORDER: Role[] = ['subwoofer', 'midbass', 'midrange', 'tweeter']
  const xoPairs = $derived.by(() => {
    const out: { a: string; b: string; lp: number | null; hp: number | null; note: string; ok: boolean }[] = []
    for (const side of ['L', 'R', '']) {
      const pick = (r: Role) => used.find((c) => c.role === r && (side === '' || r === 'subwoofer' || c.name.includes(` ${side} `)))
      for (let i = 0; i < ORDER.length - 1; i++) {
        const lo = pick(ORDER[i]), hi = pick(ORDER[i + 1])
        if (!lo || !hi || (side === '' && ORDER[i] !== 'subwoofer')) continue
        const lp = lo.lp?.freq_hz ?? null, hp = hi.hp?.freq_hz ?? null
        let note = '', ok = true
        if (lp && hp) {
          const oct = Math.log2(lp / hp)
          if (oct < -0.15) { note = `gap of ${(-oct).toFixed(2)} oct — likely a dip`; ok = false }
          else if (oct > 0.5) { note = `overlap of ${oct.toFixed(2)} oct — check summing`; ok = false }
          else note = Math.abs(oct) < 0.05 ? 'aligned' : `${oct > 0 ? 'overlap' : 'gap'} ${Math.abs(oct).toFixed(2)} oct`
        } else note = lp ? 'upper driver has no high-pass' : 'lower driver has no low-pass'
        out.push({ a: `${lo.id} ${lo.name || lo.role}`, b: `${hi.id} ${hi.name || hi.role}`, lp, hp, note, ok })
      }
    }
    return out.filter((v, i, arr) => arr.findIndex((w) => w.a === v.a && w.b === v.b) === i)
  })
  const label = (c: Channel) => `${c.id} · ${c.name || ROLE_LABEL[c.role]}`
</script>

<div class="wizard">
  <nav class="steps" aria-label="Setup steps">
    {#each STEPS as st, i}
      <button class="step" class:now={i === step} class:done={i < step} aria-current={i === step ? 'step' : undefined} onclick={() => (step = i)}>
        <span class="dot">{i < step ? '✓' : i + 1}</span>
        <span class="txt"><b>{st.t}</b><small>{st.s}</small></span>
      </button>
    {/each}
  </nav>

  <main>
    <div class="kicker">STEP {step + 1} OF {STEPS.length}</div>
    <h1>{STEPS[step].t}</h1>

    {#if step === 0}
      <p class="muted">Confirm what each output drives. Roles set the safety rules — tweeters and mids need a high-pass, subs a subsonic filter. Change roles in Studio's inspector.</p>
      <div class="sys">
        {#each chans as c}
          <div class="panel row" class:unused={c.role === 'unused'}>
            <span class="sw" style="background:{ROLE_COLORS[c.role]}"></span>
            <b class="mono">{c.id}</b><span>{c.name || '—'}</span><span class="muted">{ROLE_LABEL[c.role]}</span>
            <span class="mono muted">{c.hp ? `HP ${fmtHz(c.hp.freq_hz)}` : ''} {c.lp ? `LP ${fmtHz(c.lp.freq_hz)}` : ''}</span>
          </div>
        {/each}
      </div>
      <p class="muted">Record the actual head unit, amplifiers and speakers (with their specs) in
        <button class="link" onclick={() => { app.mode = 'system'; document.documentElement.dataset.mode = 'system' }}>System</button>
        — a recorded driver Fs tightens that channel's minimum high-pass.</p>
    {:else if step === 1}
      <p class="muted">Each driver's average level across its band is compared with the target. Changes are limited to ±3 dB per pass — run it again after re-measuring if a driver needs more.</p>
      <button class="primary" disabled={!hasMeas || app.busy} onclick={() => app.proposeLevels()}>Propose level changes</button>
    {:else if step === 2}
      <p class="muted">Measure from the centre of each speaker to the middle of your head (between your ears) in the seat you're tuning for. The farthest speaker becomes the reference; nearer ones are delayed to match.</p>
      <div class="unit" role="group" aria-label="Units">
        <button class:on={distUnit === 'cm'} onclick={() => (distUnit = 'cm')}>cm</button>
        <button class:on={distUnit === 'in'} onclick={() => (distUnit = 'in')}>inches</button>
      </div>
      <div class="dist">
        {#each used as c}
          <label><span><span class="sw" style="background:{ROLE_COLORS[c.role]}"></span>{label(c)}</span>
            <input type="number" min="0" step="0.5" placeholder="distance" bind:value={dist[c.id]} />
          </label>
        {/each}
      </div>
      <button class="primary" disabled={app.busy} onclick={propose}>Propose delays</button>
    {:else if step === 3}
      <p class="muted">Adjacent drivers should hand over near the same frequency. Gaps cause dips; wide overlaps can cause peaks or cancellations depending on polarity and delay.</p>
      <div class="sys">
        {#each xoPairs as x}
          <div class="panel xrow" class:bad={!x.ok}>
            <span>{x.a} <span class="muted">LP</span> <b class="mono">{x.lp ? fmtHz(x.lp) : '—'}</b></span>
            <span class="muted">→</span>
            <span>{x.b} <span class="muted">HP</span> <b class="mono">{x.hp ? fmtHz(x.hp) : '—'}</b></span>
            <span class="note">{x.note}</span>
          </div>
        {/each}
      </div>
      <p class="muted">Adjust crossover points in Studio; summing with phase needs sweep measurements (coming with the REW link).</p>
    {:else if step === 4}
      <p class="muted">Fits parametric EQ to bring each measured driver toward the target's shape inside its passband. Prefers cuts; boosts are capped at +3 dB because in-car dips are often cancellations.</p>
      <div class="row-btns">
        <button class="primary" disabled={!hasMeas || app.busy} onclick={() => app.proposeAutoEq(null)}>Propose EQ for all drivers</button>
        <button disabled={!hasMeas || app.busy} onclick={() => app.proposeAutoEq(null, { max_freq: 1000 })}>Only below 1 kHz</button>
      </div>
    {:else}
      <p class="muted">Save this tune as a scene, set it as A and an earlier tune as B (Scenes menu), then switch with the A/B button while music plays.</p>
      <div class="row-btns">
        <button class="primary" onclick={() => { const n = prompt('Save this tune as…'); if (n) app.saveSnapshot(n) }}>Save as scene…</button>
        <button onclick={() => app.setAB('A', null)}>Set A = this tune</button>
        <button disabled={!(app.status?.ab.A && app.status?.ab.B)} onclick={() => app.toggleAB()}>Switch A/B</button>
      </div>
    {/if}

    {#if step >= 1 && step <= 4}
      <div class="panel graph"><Graph compact /></div>
    {/if}

    <div class="nav">
      <button disabled={step === 0} onclick={() => step--}>Back</button>
      <button class="primary" disabled={step === STEPS.length - 1} onclick={() => step++}>Next</button>
    </div>
  </main>

  <aside class="side">
    <ProposalCard />
    <div class="panel copilot">
      <div class="ch"><b>Copilot</b><span class="muted">HTTP API · MCP</span></div>
      <p class="muted">Any MCP-capable agent can run these steps — proposals it makes appear here for you to apply. In-app chat with a selectable model (cloud or the truck's local model) comes later.</p>
    </div>
  </aside>
</div>

<style>
  .wizard { display: grid; grid-template-columns: 250px minmax(0, 1fr) 360px; gap: 16px; padding: 16px; }
  @media (max-width: 1100px) { .wizard { grid-template-columns: minmax(0, 1fr); } .steps { flex-direction: row !important; overflow-x: auto; } }
  @media (horizontal-viewport-segments: 2) { .wizard { grid-template-columns: env(viewport-segment-width 0 0) env(viewport-segment-width 1 0); } .steps { grid-column: 1 / -1; flex-direction: row !important; } }
  main { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  main p { margin: 0; max-width: 70ch; line-height: 1.5; }
  .steps { display: flex; flex-direction: column; gap: 4px; }
  .step { all: unset; cursor: pointer; display: flex; gap: 12px; align-items: center; padding: 10px; border-radius: 10px; color: var(--muted); }
  .step:focus-visible { outline: 2px solid var(--accent); }
  .step.now { background: var(--panel); color: var(--ink); }
  .step.done { color: var(--ink); }
  .dot { width: 28px; height: 28px; flex: none; border-radius: 50%; display: grid; place-items: center; background: var(--panel-2); font-weight: 600; font-size: 13px; }
  .step.done .dot { background: var(--accent); color: var(--accent-ink); }
  .step.now .dot { background: var(--ink); color: var(--bg); }
  .txt { display: flex; flex-direction: column; white-space: nowrap; }
  .txt small { font-size: 12px; color: var(--dim); }
  .kicker { color: var(--accent-text); font-size: 13px; font-weight: 600; letter-spacing: .06em; }
  h1 { margin: 0; font-size: 26px; }
  .sys { display: flex; flex-direction: column; gap: 6px; }
  .row { display: grid; grid-template-columns: 14px 24px 1.4fr 1fr 1.3fr; gap: 10px; align-items: center; padding: 10px 12px; }
  .row.unused { opacity: .5; }
  .sw { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .row .sw { margin: 0; }
  .unit { display: flex; gap: 6px; }
  .dist { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
  .dist label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
  .xrow { display: grid; grid-template-columns: 1fr auto 1fr 1.2fr; gap: 10px; align-items: center; padding: 10px 12px; font-size: 14px; }
  .xrow.bad { border-color: var(--warn); }
  .xrow.bad .note { color: var(--warn); }
  .note { font-size: 13px; color: var(--muted); }
  .row-btns { display: flex; flex-wrap: wrap; gap: 8px; }
  .graph { height: 300px; padding: 8px; }
  .nav { display: flex; gap: 10px; }
  .link { all: unset; color: var(--accent-text); cursor: pointer; text-decoration: underline; }
  .side { display: flex; flex-direction: column; gap: 16px; }
  .copilot { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
  .ch { display: flex; justify-content: space-between; align-items: baseline; }
  .copilot p { font-size: 14px; line-height: 1.5; margin: 0; }
</style>
