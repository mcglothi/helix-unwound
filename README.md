# helixtune

Open replacement for Audiotec Fischer's Windows-only DSP PC-Tool, for the
**HELIX DSP PRO MK2**: a headless tuning engine with a web UI (desktop and phone)
and an MCP server, so a person and an AI agent can tune the same system together.

Status: protocol and parameter map reverse-engineered statically from PC-Tool
4.80b (see `notes/FINDINGS.md`). **Not yet verified on hardware.** Every
unverified assumption is marked PROVISIONAL in code; `docs/capture-checklist.md`
is the plan to confirm them.

## Run

```bash
uv sync
uv run helixtune serve                 # http://127.0.0.1:8765
uv run helixtune serve --host 0.0.0.0  # reachable from your phone on the LAN
```

The parameter map (`DSPPro2.at01`) ships inside the vendor installer and is not
included here. `serve` finds it in `artifacts/extracted/app/deviceFiles/`,
`~/.helixtune/`, `$HELIXTUNE_AT01`, or `--at01 PATH`.

State lives in `~/.helixtune/` (`current.json`, `snapshots/`, `safety.json`,
`events.jsonl`).

## Hardware

```bash
uv run helixtune ports
uv run helixtune probe          # read-only: sends only the identify command
```

In the UI, connect to the serial port **without** "writes" first. To make the
engine own the DSP, connect with writes and use **Overwrite DSP…** — this replaces
the tune on the unit, so save/import your current tune first.

## Agent (MCP)

With `serve` running:

```bash
claude mcp add helixtune -- uv run --project ~/code/helix-dsp helixtune mcp
```

Tools: overview, per-channel read/write, crossovers, EQ bands, master gain,
predicted response, undo, snapshots, safety policy. Agents cannot do a full
overwrite and cannot change the safety policy.

## Safety

Enforced in the engine for every client (`~/.helixtune/safety.json`):
role-based minimum high-pass (tweeter ≥ 1.5 kHz, mid ≥ 150 Hz, …), max EQ boost,
max channel/master gain, max boost increase per step, no unmuting with positive
gain. Nothing is written to a device until a person confirms a full overwrite.

## Layout

```
src/helixtune/
  protocol/   frame codec, commands, client (writes off by default)
  devicefile.py  .at01 / .AF1 loaders
  dsp/        8.24 fixed point, EQ + crossover filter design
  model.py    the tune (pydantic)
  mapping.py  tune -> DSP RAM image, diff, write coalescing
  safety.py   limits
  engine.py   single owner of state, device, history, snapshots
  api.py      HTTP API + web UI
  mcp_server.py
  emulator.py stand-in device for development and tests
```
