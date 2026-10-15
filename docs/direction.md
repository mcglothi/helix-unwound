# helixtune — Product Direction

Last Updated: 2026-10-15
Status: draft for discussion. Nothing here is built yet beyond what the README lists.

## Why this exists (and why now)

- Audiotec Fischer moved on. **DSP PC-Tool 6** (EISA 2025–26) has a signal-path UI,
  a built-in RTA, mic measurement via their AMI interface, "TuneEQ" and fully automatic
  **Tune To Target**, and Dynamic Loudness. It supports "all ATF DSPs since 2018".
  The DSP PRO MK2 is older than that and stays on **PC-Tool 4**, which is Windows-only
  and has none of these features. helixtune can give the MK2 a better tool than ATF ships today.
- Across the industry (Audison bit Drive/ACCORDO, JL TüN, Zapco, Mosconi), the hardware
  is good and the software is the weak point. Forums praise Helix only for being *stable*.
  No one makes a tuning tool that looks and feels good to use.
- **REW** already measures better than any DSP vendor's tool, and it now has an HTTP
  API (`localhost:4735`, OpenAPI at `/doc.json`). Vendors stop at importing REW's EQ text
  file. We can go further and drive REW live.

## Positioning

> **A tuning bench, not a settings dialog.** helixtune is where the DSP, the measurements,
> and the target meet on one screen, and where a person and an agent tune together.

Three users of the same engine:
1. **You at the laptop**: a full workstation view with REW driving the mic.
2. **You in the driver's seat**: a phone controller with big targets, A/B, a volume knob,
   and a "measure here" button.
3. **An agent (MCP)**: proposes changes, runs measure → adjust → verify loops, and can
   never exceed the safety policy.

## Design principles

1. **Predict, then verify.** Every edit updates a *predicted* curve right away; every
   measurement overlays the *measured* curve. Your tune is the gap between them and
   the target. No vendor shows all three together.
2. **The signal path is the navigation.** As in PC-Tool 6: Inputs → Routing → Virtual
   channels → Outputs, with every block clickable. Unlike PC-Tool 6, each block shows a
   live summary (slope, delay, EQ count, gain) so the overview *is* the status.
3. **Physical over abstract.** Delay is entered as distance in a top-down car diagram
   (seat position, speaker locations), and ms/samples are derived from it. Polarity and
   phase are shown at the crossover point, not as a checkbox.
4. **Nothing is lost.** Every change is an event. Unlimited undo, named snapshots,
   and a tune timeline you can scrub ("what did it sound like Tuesday?").
5. **Safe by construction.** The existing safety policy stays in the engine and is
   *visible* in the UI: red zones on the HPF slider and a boost budget per channel.
6. **Beautiful is a feature.** Dark-first instrument aesthetic, smooth 60 fps graphs,
   restrained color: one hue per driver role, kept consistent everywhere.

## Information architecture

```
┌ Top bar: device state · active preset (A/B) · master volume · undo · snapshot · agent status
├ Left rail: SIGNAL PATH (inputs → matrix → channels), each with a live mini-summary
├ Center: the GRAPH (magnitude / phase / group delay / IR-ETC tabs)
│         layers: target · predicted · measured · sum · per-driver
├ Right: INSPECTOR for the selected block (crossover, EQ bands, delay, gain, polarity)
└ Bottom drawer: Timeline (events/snapshots) · Measurements library · Agent log
```

Phone layout: graph on top, inspector as a bottom sheet, and a persistent
transport (A/B, mute group, volume, measure).

## Feature map

### Tier 1: core bench (makes it better than PC-Tool 4)
- Signal-path overview with live block summaries
- Interactive EQ graph (FabFilter-style): drag nodes, scroll for Q, alt-click to bypass a band,
  floating band controls, multi-select, band-count/boost budget per channel
- Crossover editor showing both sides of the crossover, predicted acoustic sum, and phase overlay
- Delay by distance: top-down car diagram, listening-position presets (Driver / Passenger / Center / Both)
- Channel linking (L/R gang with offset), solo/mute groups, polarity
- Snapshots + A/B compare + event timeline (backed by the existing `events.jsonl`)
- Import/export **`.afpx`**, so your 2017–18 tunes (`BasicTune - DRV-TA.afpx` etc.) load on day one
- REW Generic EQ text import/export (what every vendor supports)

### Tier 2: REW integration (no one else does this)
- **Live REW bridge** via the REW API: list/pull measurements, trigger sweeps (REW Pro),
  import impulse responses. Measurements show up on the graph as layers.
- **Per-driver measurement wizard**: solo each output in turn → REW sweeps → tagged
  measurement (driver, side, mic position). Uses a timing reference so arrival times mean something.
- **Arrival-time → delay**: compute delays from IR peaks/ETC, cross-checked against the
  tape-measure value from the car diagram. Flag disagreements > 0.1 ms. Car reflections
  make IR-only alignment unreliable, so show both and let you choose.
- **Crossover alignment tool** (like REW's Alignment tool, in the DSP's own terms):
  pick two drivers, adjust delay/polarity/gain, preview the sum against the phase-ignoring
  max ("dotted line"), and apply to the DSP in one click.
- **Spatial averaging**: tag several mic positions per seat and average them (RMS or
  vector), the standard car practice
- Measurement library: ties the 2018 `01282018_REW Measurements.mdat` to the tunes it
  produced, so you can compare then and now

### Tier 3: assisted tuning (our version of ACCORDO / Tune To Target)
- **Target curves**: Harman in-car and flat, plus tilt (−0.5 to −1 dB/oct) and bass shelf sliders;
  custom curves drawn on the graph or imported. Separate targets per listening position.
- **Auto-EQ to target** with car-specific rules: only correct deviations ≥ 3 dB, prefer
  cuts, boosts ≤ 3 dB, 5–10 bands per channel, no correction above ~a few kHz where mic
  position dominates. It *proposes* a diff that you review and apply.
- **Gain matching** of L/R and between drivers, from measurements
- **Agent loop over MCP**: "flatten passenger mid 200–600 Hz" → measure → propose →
  you approve → apply → re-measure → report. Every step is logged in the timeline.
- Optional later: multi-seat optimization (MSO-style) for subs, all-pass phase tweaks at crossovers

### Tier 4: in-car life
- Phone remote with presets per source/seat (like Audison's "Preferential Memories")
- Dynamic loudness (two-band, level-dependent), if the MK2 DSP program has room for it
- Tuning-track player with a checklist (pink noise, sweeps, imaging tracks, vocal center test)
- Listening notes pinned to timeline moments ("vocal pulls left at 1:20")

## Visual language (first pass)

- Dark graphite background, one accent color for "you are editing this"
- Role colors kept everywhere: **sub** deep violet · **mid-bass** amber · **mid** teal ·
  **tweeter** sky · **target** white dashed · **predicted** solid · **measured** dotted with a ±spread band
- Typography: a tabular-figure mono for numbers (so values don't jitter while dragging),
  a humanist sans for labels
- Motion: curves morph between states (A/B, undo) instead of jumping, so you can *see* what changed

## Technical implications for the current code

| Need | Where | Note |
|---|---|---|
| Predicted acoustic response (incl. phase) | `dsp/filters.py`, `engine.py` | Already magnitude; add complex response, delay, polarity |
| Measurement model + storage | new `measure/` | REW API client, IR/FR import, tags, averaging |
| `.afpx` reader/writer | new `presets/afpx.py` | Open item in FINDINGS; 8 real samples now exist on feynman |
| Event timeline | `events.jsonl` | Already exists; needs snapshots linked to events |
| UI | `web/index.html` (12 KB) | Outgrowing one file; move to a small component build (Svelte or Preact + canvas/WebGL graph) |
| MCP | `mcp_server.py` | Add measure/propose/apply tools, still gated by safety |

## Open decisions

1. **UI stack**: Svelte vs Preact vs keeping a no-build page. (Recommendation: Svelte + a
   custom canvas graph; the graph is the product and should not depend on a charting library.)
2. **REW Pro license**: the API needs Pro to trigger sweeps; reading and importing works without it.
   Do you have Pro?
3. **Mic**: which measurement mic and cal file (UMIK-1?), and is it on the Dell?
4. **Does the Dell run PC-Tool 4?** Useful for protocol captures *and* for checking that
   helixtune's `.afpx` round-trips byte-exact.

## Sources

- ATF DSP PC-Tool 6 — https://www.audiotec-fischer.de/en/blog/detail/sCategory/77/blogArticle/72 , https://eisa.eu/awards/dsp-pc-tool-6/
- Audison bit Drive 2 / ACCORDO — https://audioxpress.com/news/audison-boosts-in-car-dsp-with-new-auto-tuning-software , https://audison.com/bit-drive/
- REW API — https://www.roomeqwizard.com/help/help_en-GB/html/api.html , https://www.avnirvana.com/threads/rew-api-beta-releases.12981/
- REW Alignment tool — https://avnirvana.com/threads/rew-alignment-tool-guides-or-manual.6814/page-8
- Car tuning workflow / targets — https://audiointensity.com/blogs/how-to-tune/car-audio-dsp-step-by-step-eq , https://audiointensity.com/blogs/how-to-test/rew-car-audio-beginner-to-advanced
- Smaart delay finder / coherence — https://support.rationalacoustics.com/support/solutions/articles/150000188314
- FabFilter Pro-Q Spectrum Grab — https://prod.fabfilter.com/help/pro-q/using/spectrumgrab
- MSO / rePhase — https://www.avnirvana.com/threads/mso-multi-sub-optomizer.1891 , https://www.diyaudio.com/forums/software-tools/221434-rephase-loudspeaker-phase-linearization-eq-fir-filtering-tool.html
- Forum consensus on vendor software — https://www.diymobileaudio.com/threads/audio-control-vs-helix-vs-audison-dsp.470509/
- Dirac automotive workflow — https://dirac.com/dirac-vr
