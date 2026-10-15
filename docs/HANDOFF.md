# helixTune handoff

Last Updated: 2026-10-15
Status: ⚠️ IN PROGRESS — foundation milestone 1
Current owner: Codex CLI (release ownership in AIKB when handing off)
Branch: `pi/helixtune-foundation`

## Resume

1. Read this document and `AGENTS.md`; inspect `git status` and `git log -5 --oneline`.
2. Check AIKB active claims before editing. Only one agent edits this checkout at a time.
3. Continue the next task below. User authorized local checkpoint commits; no push/publication.
4. Update this document and the AIKB index at the next complete milestone.

## Approved direction

- Target HELIX DSP PRO MK2; Mac-first workstation backed by a headless Python engine with HTTP/MCP and a Svelte client. Preserve Linux/truck-computer viability.
- Studio Console visual direction, consistent themes, Drive/Setup/System views, phone/tablet/desktop support, foldables considered.
- REW alongside tuning, proposals and verification, legacy preset/measurement imports, equipment and wiring model.
- Codex and Claude alternate on this branch with milestone checkpoints. Current priority: foundation reliability before more features.
- All hardware semantics remain provisional; Windows capture session is still needed. No hardware accessed during Codex review/setup.

## Checkpoints

- `a642b9b` — initial Claude prototype preserved (88 files). Excludes private/vendor inputs and generated frontend assets. Baseline: 64 Python tests pass locally; previous review also found 12 frontend tests passing and clean Svelte/TS checks.
- Collaboration setup — this document plus local `AGENTS.md`; use `git log` for its commit.

## Current milestone: device writes and physical channel identity

⚠️ IN PROGRESS

- Invalidate device baseline after any failed write; retain last accepted application tune.
- Expose uncertain state to clients and require deliberate full resynchronization before more incremental writes.
- Recheck tune validity and protection policy on full push.
- Ensure channel IDs determine hardware mapping; reject missing, duplicate, and unknown outputs and unsupported sample rates.
- Keep undo/snapshot/A-B bookkeeping unchanged if a device write fails.
- Add synthetic-address regressions that require no vendor inputs.

## Next tasks after this milestone

1. Protection/authority boundary: role metadata can currently weaken checks; MCP exposes role changes and the HTTP source header is not authentication. Design persistent physical-output protection settings and capabilities before implementing a superficial agent-only restriction.
2. Proposal conflicts: `before` is stored but not checked; bind affected fields and measurement assumptions to preview and reject stale application.
3. Prediction integrity: master gain omitted, overlapping measurements double-counted, phase-blind sums cannot establish crossover alignment. Make limitations visible and preserve measurement provenance.
4. Verify hardware protocol from Windows captures before live writes: addresses, coefficient sign, fixed-point format, delay/mute/routing semantics, ACK validation, safeload/atomic updates, readback and reconnect behavior.

These are review recommendations, not approval for every proposed product feature. See `docs/DESIGN.md` for prior choices and compare against implementation; design docs contain aspirational/unverified claims.

## Reproduction and validation

- `uv sync`; Python tests: `uv run pytest -q`.
- `cd web && npm ci && npm run check && npm test && npm run build`.
- `uv run helixtune serve` serves built Svelte UI when available; use a temporary `--data` directory for experiments.
- Local private inputs: ignored `artifacts/extracted/app/deviceFiles/DSPPro2.at01` and ignored `captures/backups-2018/`. Some original tests skip when these are missing. New foundation regressions must remain runnable without them.
- No Git remote is configured. All checkpoints are local.

## Known limits at handoff

- No protocol/hardware verification yet. Emulator and engine share provisional assumptions.
- UI was source-reviewed; Codex could not inspect a rendered browser session in this environment.
- Current event summaries cannot reconstruct a full tune timeline after restart.
- Legacy preset crossover/mute/delay interpretation remains provisional.
- Do not infer exact historical measurement-to-tune association from file dates alone.
