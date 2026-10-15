# HelixTune — product direction

Last updated: 2026-10-15

## What we're building

A measurement-driven tuning workstation for the HELIX DSP PRO MK2 that a person
and an AI agent use together, alongside REW. It runs the same way on a Mac, a
phone, and (later) a small computer in the truck with a UMIK-1.

The goal is not to copy PC-Tool. It should do what the best current tools do
(PC-Tool 6's signal-path layout and Tune-to-Target, Audison's guided wizard,
Dirac's draggable target curves, AudioControl's built-in analysers) and add what
none of them do: **predict the acoustic result of a change before making it**, and
expose everything to an agent.

## What the market does (Oct 2026)

| Tool | Ideas worth taking | Gaps |
|------|--------------------|------|
| Audiotec Fischer **DSP PC-Tool 6** (EISA 2025-26) | Layout follows the signal path: inputs → virtual channels → outputs. TuneEQ fits PEQ bands to a measurement; *Tune To Target* automates EQ **and gain** to any target curve. Input signal analyser to detect OEM EQ. | Doesn't support the PRO MK2 (ACO-only). Windows-only. Mic measurement needs their AMI interface. |
| **Audison bit Drive / ACCORDO** | Step-by-step wizard: output EQ, level, then delay with one mic. Diagnosis of wiring errors (polarity, dead channel). | Closed, single-vendor hardware. |
| **Dirac Live** | Draggable target curve; auto-target derived from the measured system; mixed-phase correction. | Home-theatre focus; not for this DSP. |
| **AudioControl DM Smart DSP** | Built-in input/output RTA inside the DSP software; auto-EQ shows the applied curve under the result. | Electrical only; acoustic still needs a separate mic. |
| **REW** (our measurement engine) | Everything: sweeps, RTA, impulse/phase, averaging, alignment tool, EQ matching. Since 5.40 a full **HTTP API on localhost:4735** (measurements, FR/IR/GD data, averaging, alignment tool, EQ match, generator, RTA, subscriptions). Sweep automation needs REW Pro. | Doesn't control the DSP; the measure → change → re-measure loop is manual. |
| **CamillaDSP / camillaNode** | Clean web UIs, YAML-described pipeline, AutoEQ import. | Software DSP, not hardware. |

Community REW MCP servers exist; we'll talk to REW's API directly from the engine
so the agent sees measurements and DSP state in one place.

## Core idea: measure once, predict everything

Every measurement is stored with **the exact tune that was active when it was
taken**. Because we compute every filter ourselves, the engine can predict the
in-car response of any later tune:

```
predicted(f) = measured(f) × H_new(f) / H_at_measurement(f)
```

Magnitude works from RTA data; with sweep data (phase), we also get predicted
**summation between drivers**, so crossover points, delays and polarity can be
judged on screen before you go back to the truck. Re-measuring then confirms it.

## Features

### 1. Signal-path workspace
- **Inputs** → **routing matrix** (12×12, from the preset's `Route`) → **outputs**
  (10 used + 2 aux), each stage on its own screen, in the same order as the audio.
- Channel strips like a mixing console: name, role, colour, level meter area,
  mute/solo, polarity, delay, crossover, EQ. Mobile: one strip at a time, swipe.
- **Link groups** (the preset's `LG`): link L/R pairs so EQ/crossover edits mirror.
- **Delay groups** (`DG`): move a group's delay together.

### 2. The graph
- One large log-frequency graph: target curve, measured response, predicted
  response, filter curve, per-driver curves, and the summed system.
- Drag EQ nodes directly on the curve; scroll/pinch adjusts Q. Crossover handles.
- Phase / group-delay views when sweep data is present.
- Optional per-seat views (driver, passenger, centre average).

### 3. Measurements (REW)
- Connect to REW's API; list, pull, and overlay measurements live.
- Tag each measurement with channel(s), seat and mic position; snapshot the tune.
- Import legacy `.mdat` (done: 2018 RTA captures decode) and REW text exports.
- Guided sequences: "measure each driver alone at the driver's seat" — the engine
  mutes/unmutes channels, REW measures (Pro) or you press measure.
- Spatial averaging (moving-mic or multi-position) via REW's averaging.

### 4. Targets
- Library: flat, gentle tilt, car "preference" curve (bass shelf +6–10 dB below
  ~100 Hz, −0.5…−1 dB/oct downward tilt), and imported REW house curves.
- Drag to edit; save per car / per seat.

### 5. Auto-tune (Tune-to-Target, but safe)
- Fit PEQ bands per channel to the target using the predicted response.
- Constraints: prefer cuts, cap boosts (safety policy), Q limits, band budget,
  correct mostly below a chosen frequency (in-car reflections make narrow
  high-frequency fixes position-dependent).
- Level matching between drivers, then delay from measured arrival times or
  entered distances, then polarity/phase check across each crossover.
- Always proposed as a **diff you review** (or the agent explains) before applying.

### 6. Scenes & A/B
- Scenes = full tunes for listening positions (your DRV-TA / PAS-TA presets).
- Instant A/B (and blind A/B) between two scenes or between "now" and a snapshot.
- Every change journaled with who made it (you / agent), why, and the measurement
  that motivated it. Restore any point.

### 7. Agent
- MCP tools already cover editing; add: list/pull measurements, predicted
  response vs target, propose auto-EQ, run a guided measurement step, explain.
- In-app copilot panel later.
- Agents never bypass the safety policy, never do a full overwrite, never flash
  firmware.

### 8. Import / export
- **`.afpx` import** (your 2017-18 tunes) — and **export**, so the original PC-Tool
  can still load what we make.
- REW filter text export/import.

### 9. Truck mode (later)
- Small computer + UMIK-1 + the DSP over USB; Wi-Fi hotspot serves the same UI.
- Continuous RTA with music as the test signal; slow, bounded, reversible
  adjustments (e.g. road-noise bass compensation) within hard limits.

## Decisions (2026-10-15)

- **Base look: Direction A "Studio Console"** — warm charcoal, amber accent, IBM Plex
  Sans/Mono, big graph + inspector + channel strips. Mockups:
  https://claude.ai/artifact/XHXtisNXvZ35hYbeidgSKQ
- **Drive mode** borrows Direction C: black, oversized touch targets, top-down cab view,
  seat switch, live RTA. Same app, a mode, not a separate product.
- **Guided + copilot (D)** becomes the **setup wizard** and an optional assist panel:
  setup → levels → time alignment → crossovers → EQ to target → listen/A-B.
- **Form factors:** phone, tablet, desktop, and foldables. Layout is driven by available
  width and by viewport segments (`horizontal-viewport-segments` /
  `vertical-viewport-segments`): on a folded-open device the graph sits on one panel and
  the controls on the other, never across the hinge.
- **Agents: tool layer first, brain pluggable.** Every capability is an HTTP endpoint
  and an MCP tool. External agents (any window) use MCP now. An in-app copilot panel,
  later, calls the same tools through a provider interface: Claude API, or an
  OpenAI-compatible local endpoint (llama.cpp / Ollama) on the truck computer.
- **Vehicle signals (later):** a generic signal bus (speed, RPM, gear, ignition) fed by
  an OBD-II adapter (ELM327 via python-OBD). Uses: speed-dependent bass/road-noise
  compensation within safety limits, quiet-at-idle checks, logging tuning context.

- **System mode (whole audio system, not just the DSP):** equipment inventory (source,
  DSP, amps, speakers, subs, enclosures, mic, power, in-truck computer) with make/model/
  serial/location and a specs table where every value carries its source; wiring between
  components by signal type; an auto-laid-out diagram (source → processing → amps →
  drivers). Agents look up manufacturer datasheets and record T/S parameters with source
  URLs. Recorded driver Fs feeds the safety policy (role-based factor: tweeter 2×Fs,
  midrange 1.5×, midbass/woofer 1×); enclosure + T/S give sealed Qtc/F3 and ported
  subsonic guidance.
- **Themes:** base16 schemes map onto semantic tokens with contrast correction; built-ins
  plus imports shared via the engine; per-device choice and optional Drive-mode theme.
  Drive mode uses the same theme, only larger.

- **System designer (canvas):** Svelte Flow (xyflow) node editor. Typed, colour-coded ports
  per component kind (ports.ts); while dragging a wire, incompatible ports dim and
  compatible ones grow (Blender/Fuser socket conventions); plugging into an occupied single
  input replaces the old wire; dropping a wire on empty canvas opens a "add a connected…"
  menu (Blender link-drag-search); drag-from-palette onto the canvas; snap-to-grid,
  minimap, zoom/fit, Delete key, auto-arrange (dagre, left→right signal order).
  Two views: Signal flow, and Vehicle (components as photo pins over a cab photo).
  Media library (local, images only, no SVG) for device/cab photos; components can also
  reference a stock image URL.

- **Gain staging (planned):** amp gains only match the DSP's output voltage to each amp's
  input sensitivity; playback level and driver power limits are set in the DSP. A helper
  will walk through setting gains (test tone, voltage target from amp power × load) and
  warn when an amp can deliver more than a driver's rating (e.g. SCV-1500D at 1 Ω ≈ 750 W
  per SD-3 10 vs 500 W RMS), so the DSP-side level ceiling can be set accordingly.

## Look and feel
- Dark "instrument panel" default with a light theme; one accent colour per driver
  group (sub, midbass, mid, tweeter), left and right as shades of the same hue.
- The graph is the hero; controls are large enough for a thumb in a car.
- No modal dialogs except destructive confirmations.

## Frontend tech
Move from the single HTML file to **Svelte + Vite** with a fast canvas plot
library, built to static files the engine serves (no internet needed in the truck).

## Order of work
1. `.afpx` import/export (needs attribute semantics → REA) + scenes.
2. Measurements: `.mdat`/REW import, storage with tune snapshot, overlay.
3. Prediction engine + target curves + new graph.
4. Frontend rebuild (Svelte) around the graph and channel strips.
5. Auto-tune proposals, level/delay/polarity helpers.
6. REW live API integration and guided measurement sequences.
7. Agent tools for all of the above.
8. Truck mode.
