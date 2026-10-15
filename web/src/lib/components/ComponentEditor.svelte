<script lang="ts">
  import { app } from '../state.svelte'
  import type { Analysis, Kind, Signal } from '../types'
  import { KIND_LABEL, SIGNAL_STYLE } from '../types'
  import { mediaUrl } from '../designer/drag.svelte'

  let photoInput = $state<HTMLInputElement>()
  let stockUrl = $state('')
  async function addPhotos(e: Event) {
    const files = [...((e.currentTarget as HTMLInputElement).files ?? [])]
    if (!c) return
    const ids: string[] = []
    for (const f of files) {
      const m = await app.uploadMedia(f, c.name)
      if (m) ids.push(m.id)
    }
    if (ids.length) app.patchComponent(c.id, { media: [...c.media, ...ids], image: c.image ?? ids[0] })
  }
  function addStock() {
    if (!c || !/^https?:\/\//.test(stockUrl.trim())) return app.toast('Enter an http(s) image URL')
    const u = stockUrl.trim()
    app.patchComponent(c.id, { media: [...c.media, u], image: c.image ?? u })
    stockUrl = ''
  }
  function removePhoto(ref: string) {
    if (!c) return
    const media = c.media.filter((m) => m !== ref)
    app.patchComponent(c.id, { media, image: c.image === ref ? (media[0] ?? '') : c.image } as any)
  }

  const c = $derived(app.design?.components.find((x) => x.id === app.selectedComponent))
  const fields = $derived(c ? app.specFields[c.kind] ?? {} : {})
  const extra = $derived(c ? Object.keys(c.specs).filter((k) => !(k in fields)) : [])
  const enclosures = $derived(app.design?.components.filter((x) => x.kind === 'enclosure') ?? [])
  const wires = $derived(app.design?.connections.filter((w) => c && (w.src === c.id || w.dst === c.id)) ?? [])
  const nameOf = (id: string) => {
    const x = app.design?.components.find((y) => y.id === id)
    return x ? x.name || [x.make, x.model].filter(Boolean).join(' ') || KIND_LABEL[x.kind] : id
  }

  let analysis = $state<Analysis | null>(null)
  $effect(() => {
    const id = c?.id
    void app.status?.revision
    analysis = null
    if (id && (c?.kind === 'speaker' || c?.kind === 'subwoofer')) app.analyze(id).then((a) => (analysis = a)).catch(() => {})
  })

  function setSpec(key: string, value: string, unit: string) {
    if (!c) return
    const v = value.trim()
    const num = Number(v)
    const prev = c.specs[key]
    app.patchComponent(c.id, { specs: { [key]: v === '' ? null : { value: v !== '' && !isNaN(num) ? num : v, unit, source: prev?.source || 'manual' } } })
  }
  function setSource(key: string, source: string) {
    if (!c || !c.specs[key]) return
    app.patchComponent(c.id, { specs: { [key]: { ...c.specs[key], source } } })
  }
  let newKey = $state('')
  let newVal = $state('')

  // add wire
  let wDst = $state('')
  let wSig = $state<Signal>('speaker')
  let wPort = $state('')
  let wCable = $state('')
  const others = $derived(app.design?.components.filter((x) => x.id !== c?.id) ?? [])
  const CH = 'ABCDEFGHIJ'.split('')
  const KINDS = Object.keys(KIND_LABEL) as Kind[]
</script>

{#if c}
  <section class="panel ed" aria-label="Component details">
    <header>
      <select value={c.kind} aria-label="Kind" onchange={(e) => app.patchComponent(c.id, { kind: e.currentTarget.value as Kind })}>
        {#each KINDS as k}<option value={k}>{KIND_LABEL[k]}</option>{/each}
      </select>
      <button class="ghost danger" onclick={() => confirm(`Remove ${c.name || 'this component'} and its wiring?`) && app.deleteComponent(c.id)}>Remove</button>
    </header>

    <div class="g2">
      <label>Name<input value={c.name} onchange={(e) => app.patchComponent(c.id, { name: e.currentTarget.value })} /></label>
      <label>Location<input value={c.location} placeholder="e.g. driver door" onchange={(e) => app.patchComponent(c.id, { location: e.currentTarget.value })} /></label>
      <label>Make<input value={c.make} onchange={(e) => app.patchComponent(c.id, { make: e.currentTarget.value })} /></label>
      <label>Model<input value={c.model} onchange={(e) => app.patchComponent(c.id, { model: e.currentTarget.value })} /></label>
      <label>Serial<input value={c.serial} onchange={(e) => app.patchComponent(c.id, { serial: e.currentTarget.value })} /></label>
      <label>Datasheet URL<input value={c.spec_source} placeholder="https://…" onchange={(e) => app.patchComponent(c.id, { spec_source: e.currentTarget.value })} /></label>
    </div>

    <div class="label">Photos</div>
    <div class="photos">
      {#each [...new Set([c.image, ...c.media].filter(Boolean))] as ref (ref)}
        <div class="ph" class:primary={ref === c.image}>
          <button class="pick" title={ref === c.image ? 'Main photo' : 'Use as main photo'} aria-label="Use as main photo"
                  onclick={() => app.patchComponent(c.id, { image: ref })}><img src={mediaUrl(ref)} alt="" /></button>
          <button class="rm" aria-label="Remove photo" onclick={() => removePhoto(ref!)}>×</button>
        </div>
      {/each}
      <button class="add" onclick={() => photoInput?.click()}>+ Photo</button>
      <input bind:this={photoInput} type="file" accept="image/*" multiple hidden onchange={addPhotos} />
    </div>
    <div class="addspec">
      <input placeholder="or paste a product / stock image URL" bind:value={stockUrl} aria-label="Image URL" />
      <button disabled={!stockUrl.trim()} onclick={addStock}>Add</button>
    </div>

    {#if c.kind === 'speaker' || c.kind === 'subwoofer'}
      <fieldset>
        <legend>Fed by DSP outputs</legend>
        <div class="chans">
          {#each CH as x}
            {@const on = c.channels.includes(x)}
            <button class:on aria-pressed={on} onclick={() => app.patchComponent(c.id, { channels: on ? c.channels.filter((y) => y !== x) : [...c.channels, x] })}>{x}</button>
          {/each}
        </div>
      </fieldset>
      <label>Enclosure
        <select value={c.enclosure ?? ''} onchange={(e) => app.patchComponent(c.id, { enclosure: e.currentTarget.value || null } as any)}>
          <option value="">— none / door / not recorded —</option>
          {#each enclosures as en}<option value={en.id}>{en.name || 'Enclosure'}</option>{/each}
        </select>
      </label>
    {/if}

    {#if Object.keys(fields).length || extra.length}
      <div class="label">Specifications</div>
      <div class="specs">
        {#each Object.entries(fields) as [k, f]}
          {@const s = c.specs[k]}
          <label class="spec"><span>{f.label}{f.unit ? ` (${f.unit})` : ''}</span>
            <input value={s?.value ?? ''} onchange={(e) => setSpec(k, e.currentTarget.value, f.unit)} />
            {#if s}<input class="src" value={s.source} aria-label="{f.label} source" title="Where this value came from"
                          onchange={(e) => setSource(k, e.currentTarget.value)} />{/if}
          </label>
        {/each}
        {#each extra as k}
          {@const s = c.specs[k]}
          <label class="spec"><span>{k}{s.unit ? ` (${s.unit})` : ''}</span>
            <input value={s.value} onchange={(e) => setSpec(k, e.currentTarget.value, s.unit)} />
            <input class="src" value={s.source} aria-label="{k} source" onchange={(e) => setSource(k, e.currentTarget.value)} />
          </label>
        {/each}
      </div>
    {/if}
    <div class="addspec">
      <input placeholder="other spec (name)" bind:value={newKey} aria-label="New spec name" />
      <input placeholder="value" bind:value={newVal} aria-label="New spec value" />
      <button disabled={!newKey.trim() || !newVal.trim()} onclick={() => { setSpec(newKey.trim(), newVal, ''); newKey = ''; newVal = '' }}>Add</button>
    </div>
    {#if (c.kind === 'speaker' || c.kind === 'subwoofer') && !c.specs.fs}
      <p class="hint">Ask the agent: “look up the specs for my {c.name || 'driver'}” — it records manufacturer values with their source. A recorded Fs sets this channel's minimum high-pass.</p>
    {/if}

    {#if analysis?.findings.length}
      <div class="label">Analysis</div>
      <ul class="findings">{#each analysis.findings as f}<li>{f}</li>{/each}</ul>
    {/if}

    <label>Notes<textarea rows="2" onchange={(e) => app.patchComponent(c.id, { notes: e.currentTarget.value })}>{c.notes}</textarea></label>

    <div class="label">Wiring</div>
    <ul class="wires">
      {#each wires as w (w.id)}
        <li>
          <span class="sw" style="background:{SIGNAL_STYLE[w.signal].color}"></span>
          <span>{w.src === c.id ? '→' : '←'} {nameOf(w.src === c.id ? w.dst : w.src)}
            <small class="muted">{SIGNAL_STYLE[w.signal].label}{w.src_port ? ` · ${w.src_port}` : ''}{w.cable ? ` · ${w.cable}` : ''}{w.notes ? ` · ${w.notes}` : ''}</small></span>
          <button class="ghost x" aria-label="Remove wire" onclick={() => app.deleteConnection(w.id)}>×</button>
        </li>
      {/each}
    </ul>
    <div class="addwire">
      <select bind:value={wDst} aria-label="Connect to"><option value="">Connect output to…</option>{#each others as o}<option value={o.id}>{nameOf(o.id)}</option>{/each}</select>
      <select bind:value={wSig} aria-label="Signal">{#each Object.entries(SIGNAL_STYLE) as [k, v]}<option value={k}>{v.label}</option>{/each}</select>
      <input placeholder="port (e.g. CH1)" bind:value={wPort} aria-label="Output port" />
      <input placeholder="cable (e.g. 12 AWG)" bind:value={wCable} aria-label="Cable" />
      <button disabled={!wDst} onclick={() => { app.addConnection({ src: c.id, dst: wDst, signal: wSig, src_port: wPort, cable: wCable }); wDst = ''; wPort = ''; wCable = '' }}>Add wire</button>
    </div>
  </section>
{:else}
  <section class="panel ed empty"><p class="muted">Select a component in the diagram to edit it, or add one.</p></section>
{/if}

<style>
  .ed { padding: 14px; display: flex; flex-direction: column; gap: 12px; overflow: auto; }
  .empty { justify-content: center; }
  header { display: flex; gap: 8px; justify-content: space-between; }
  .danger { color: var(--warn); border-color: transparent; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  input, select, textarea { color: var(--ink); }
  textarea { background: var(--bg); border: 1px solid var(--line-2); border-radius: 6px; padding: 6px 8px; font: inherit; }
  .g2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  fieldset { border: 0; padding: 0; margin: 0; }
  legend { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  .chans { display: flex; flex-wrap: wrap; gap: 4px; }
  .chans button { min-width: 36px; min-height: 32px; padding: 0; font-family: var(--mono); }
  .specs { display: flex; flex-direction: column; gap: 6px; }
  .spec { display: grid; grid-template-columns: 1.3fr 0.8fr 1fr; gap: 6px; align-items: center; }
  .spec span { color: var(--ink); font-size: 13px; }
  .spec input { min-height: 30px; font-size: 12px; }
  .src { font-size: 11px !important; color: var(--muted) !important; }
  .addspec, .addwire { display: flex; flex-wrap: wrap; gap: 6px; }
  .addspec input, .addwire input, .addwire select { flex: 1 1 110px; min-height: 30px; font-size: 12px; }
  .hint { font-size: 13px; color: var(--muted); margin: 0; line-height: 1.5; }
  .findings { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.5; display: flex; flex-direction: column; gap: 4px; }
  .wires { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
  .wires li { display: flex; align-items: center; gap: 8px; }
  .wires small { display: block; }
  .sw { width: 10px; height: 10px; border-radius: 2px; flex: none; }
  .x { min-height: 26px; margin-left: auto; padding: 0 8px; }
  .photos { display: flex; flex-wrap: wrap; gap: 8px; }
  .ph { position: relative; }
  .ph .pick { padding: 0; min-height: 0; width: 72px; height: 72px; border-radius: 8px; overflow: hidden; border: 2px solid var(--line-2); }
  .ph.primary .pick { border-color: var(--accent); }
  .ph img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .ph .rm { position: absolute; top: -6px; right: -6px; min-height: 0; width: 22px; height: 22px; padding: 0; border-radius: 50%; font-size: 13px; line-height: 1; }
  .add { width: 72px; height: 72px; min-height: 0; border-style: dashed; font-size: 12px; }
</style>
