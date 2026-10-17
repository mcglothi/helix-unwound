# Helix Unwound

A community-built second life for the HELIX DSP PRO MK2.

Open replacement for Audiotec Fischer's Windows-only DSP PC-Tool, for the
**HELIX DSP PRO MK2**: a headless tuning engine with a web UI (desktop and phone)
and an MCP server, so a person and an AI agent can tune the same system together.

Status (2026-10-17): first PC-Tool USB captures corrected several protocol and
renderer assumptions. **Physical connections are read-only; hardware writes
are disabled** until remaining session/parameter cases are validated. Offline
editing and emulator tuning remain available. See
[`docs/HARDWARE-EVIDENCE.md`](docs/HARDWARE-EVIDENCE.md) for verified cases and gaps.
An explicit [stored-preset backup](docs/STORED-PRESET-BACKUP.md) is implemented;
Mac/DSP access at 19200 without a session still needs live validation.
Older running versions retain the incorrect command handling and must not be used
for hardware writes.

For ongoing development and review, start with [`docs/HANDOFF.md`](docs/HANDOFF.md).
The visual concept is a double helix unwinding into music notes—freedom and a second
life for the hardware. See [`docs/BRAND.md`](docs/BRAND.md) for branding exploration.
The package and CLI are currently named `helixtune`.

The **Measurements** view reviews capture-time hardware separately from installed
drivers, records owner evidence, and preserves corrections. Historical captures
are never silently relabeled to match replacements. See
[`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md) for the workflow and API.

The response graph reports selected capture sources, exclusions and coverage.
Estimates use current, non-overlapping captures with a known baseline; power sums
are explicitly phase-blind, not verified acoustic crossover alignment. See
[`docs/PREDICTION.md`](docs/PREDICTION.md).

## Try without hardware

Build the frontend as shown below, then run `uv run helixtune demo`. In a second
terminal, run `uv run helixtune open --data ~/.helixtune-demo --port 8770`.
This uses separate demo state, invented addresses and synthetic measurements;
physical device connections are disabled. See [`docs/DEMO.md`](docs/DEMO.md).

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

State lives in `~/.helixtune/`; the tune/history/A-B checkpoint is `workstation.json`,
with a previous-checkpoint recovery copy. See [`docs/SESSION-RECOVERY.md`](docs/SESSION-RECOVERY.md).

In emulator write workflows, if an update fails, the engine marks its state **uncertain** and pauses
incremental writes. The last accepted application tune is retained; later edits
are staged offline. Review the tune before a confirmed full emulator overwrite. Physical overwrites
remain disabled. This does not undo any writes that may already have
reached the DSP. A software baseline records completed write transactions, not
independent hardware readback verification. Parameter echo ACKs are checked;
remaining hardware protocol/session semantics are still incomplete.

The header's connection-status button opens **Connection & recovery**. Read-only
is the default; write connections require a named-tune review and explicit send
confirmation. The demo lets you exercise this workflow against an in-memory device.
In Measurements, **Bring measurements from REW** browses and copies captures through
REW's local API without changing REW or starting audio. See [`docs/REW.md`](docs/REW.md).

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
review and clear obsolete constraints individually, with a reason, in Studio's
output limits panel. Pending constraints enforce immediately; owner confirmation
is separate from editable source metadata. Current
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
