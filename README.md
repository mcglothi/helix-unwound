# helixtune

Open replacement for Audiotec Fischer's Windows-only DSP PC-Tool, for the
**HELIX DSP PRO MK2**: a headless tuning engine with a web UI (desktop and phone)
and an MCP server, so a person and an AI agent can tune the same system together.

Status: protocol and parameter map reverse-engineered statically from PC-Tool
4.80b (see `notes/FINDINGS.md`). **Not yet verified on hardware.** Every
unverified assumption is marked PROVISIONAL in code; `docs/capture-checklist.md`
is the plan to confirm them.

For ongoing Codex/Claude work, start with [`docs/HANDOFF.md`](docs/HANDOFF.md).

The **Measurements** view reviews capture-time hardware separately from installed
drivers, records owner evidence, and preserves corrections. Historical captures
are never silently relabeled to match replacements. See
[`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md) for the workflow and API.

## Run

```bash
uv sync
cd web && npm ci && npm run build && cd ..  # build the Svelte UI on a fresh checkout
uv run helixtune serve                 # http://127.0.0.1:8765
uv run helixtune serve --host 0.0.0.0  # reachable from your phone on the LAN
```

In a second terminal, run `uv run helixtune open` to open the authenticated local
owner workstation. Match `--data` and `--port` if you changed them on `serve`.
The command passes the owner credential through a URL fragment, which the UI
immediately removes and exchanges for an HttpOnly session cookie; it never prints
the credential. Opening the URL directly shows a sign-in screen. Network access
also requires credentials; HTTP does not encrypt them, so use a trusted network
or an encrypted tunnel. See [`docs/ACCESS.md`](docs/ACCESS.md) for access and migration.

The parameter map (`DSPPro2.at01`) ships inside the vendor installer and is not
included here. `serve` finds it in `artifacts/extracted/app/deviceFiles/`,
`~/.helixtune/`, `$HELIXTUNE_AT01`, or `--at01 PATH`.

State lives in `~/.helixtune/` (`current.json`, `snapshots/`, `safety.json`,
`events.jsonl`).

If a device update fails, the engine marks its state **uncertain** and pauses
incremental writes. The last accepted application tune is retained; later edits
are staged offline. Review the tune before using **Overwrite DSP…** to send all
managed parameters again. This does not undo any writes that may already have
reached the DSP. A software baseline records completed write transactions, not
independent hardware readback verification; protocol/ACK semantics remain provisional.

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

MCP automatically uses `auth/agent.token` in the engine's data directory. For a
custom directory, set `HELIXTUNE_DATA_DIR`; `HELIXTUNE_URL` selects another API
address. `HELIXTUNE_TOKEN` can supply a credential explicitly. Give agents the
agent credential, which cannot connect/disconnect devices, overwrite the DSP, or
reconfigure physical output limits. Audit headers do not grant permissions.

## Safety

Enforced in the engine for every client (`~/.helixtune/safety.json`):
role-based minimum high-pass (tweeter ≥ 1.5 kHz, mid ≥ 150 Hz, …), max EQ boost,
max channel/master gain, max boost increase per step, no unmuting with positive
gain. Gain/EQ ceilings apply even to outputs labeled unused. Nothing is written
to a device until an owner explicitly establishes a full-overwrite baseline.

Physical output floors live separately in `protections.json`. Existing current
tunes and equipment specifications migrate on startup; later accepted roles and
specifications can tighten limits. Relabeling a driver, muting it, deleting a
specification, or restoring a scene cannot silently relax those limits. To change
physical equipment, disconnect the device, correct its role/specifications, then
deliberately reconfigure its limits in Studio's output protection panel. Current
roles/specifications can still impose stricter limits. These are conservative
configuration checks, not proof of speaker protection or verified hardware behavior.

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
