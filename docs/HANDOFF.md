# helixTune handoff

Last Updated: 2026-10-15
Status: ✅ Foundation milestone 1 complete; ready for the next agent
Current owner: none after this checkpoint; claim ownership in AIKB before editing
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
- `1d8cbc5` — collaboration setup: this document, local `AGENTS.md`, and frontend build instructions.
- `ba4170f` — foundation milestone 1: interrupted writes, restore bookkeeping, physical output identity, synthetic regressions, and uncertain-state UI. The handoff-only commit follows this checkpoint; use `git log` for the current tip.

## Current milestone: device writes and physical channel identity

✅ COMPLETE

- Invalidate device baseline after any failed write; retain last accepted application tune.
- Expose uncertain state to clients and require deliberate full resynchronization before more incremental writes.
- Recheck tune validity and protection policy on full push.
- Ensure channel IDs determine hardware mapping; reject missing, duplicate, and unknown outputs and unsupported sample rates.
- Keep undo/snapshot/A-B bookkeeping unchanged if a device write fails.
- Add synthetic-address regressions that require no vendor inputs.

Implemented behavior:

- `DeviceState.sync_state`: disconnected / unsynchronized / applying / synchronized / uncertain; status also includes `last_error`. Existing `baselined` remains for client compatibility.
- Any write exception clears `applied_image`, invalidates `baselined`, records uncertainty, and preserves the previously accepted application tune. There is no claimed hardware rollback. Further edits are staged offline; a confirmed full overwrite is the only implemented recovery.
- All managed parameters are resent on full recovery, even if some writes may have landed. Full push revalidates the model and current safety policy before sending anything.
- Failed undo, snapshot loads, and A/B changes preserve history and slot contents. Offline restore paths now update pending-write counts too.
- Exactly one A–J channel is required; lowercase IDs normalize and valid unordered input is canonicalized. Rendering resolves physical output IDs explicitly. Only the existing 96 kHz target rate is accepted.
- The Svelte header shows a persistent failure message and unknown device state; built assets regenerated locally, excluded from Git.

Validation at this checkpoint:

- Full Python suite: **89 passed**, no skips with local private inputs present.
- New portable foundation tests: **25 passed**, also run from a clean `git archive` with no vendor files, personal backups, or built UI, using the installed environment and archived source.
- Frontend: **12 passed**; Svelte/TypeScript **0 errors, 0 warnings**; production build passed.
- `git diff --check` passed. No real device connected and no user-state directory used.

## Next tasks after this milestone

1. **Next concrete milestone — protection/authority boundary.** First inspect `safety.py`, `equipment.channel_driver_limits`, the role editor, and HTTP/MCP mutation paths. Propose a small model for persistent physical-output protection settings independent of mutable roles, with migration behavior for existing tunes. Then enforce the resulting rules consistently on edit, restore, full push, and agent calls. Role metadata can currently weaken checks; MCP exposes role changes and the HTTP source header is not authentication. Do not treat another source-header restriction as an authorization boundary. Preserve offline setup usability.
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
- “Synchronized” only means all write requests returned responses accepted by the current client. ACK content, atomicity, safeload, and readback remain unverified; this is not a hardware-verified tune.
- No automatic device mute or rollback is attempted after transport failure. Uncertainty can include partially applied filters. User must review and deliberately resynchronize.
- Role/authority bypass, combined filter headroom, stale proposals, and prediction issues remain open. This milestone does not establish speaker protection or public-release readiness.
- Current state persistence uses direct file writes; crash-safe storage and full history reconstruction remain future work.
- UI was source-reviewed; Codex could not inspect a rendered browser session in this environment.
- Current event summaries cannot reconstruct a full tune timeline after restart.
- Legacy preset crossover/mute/delay interpretation remains provisional.
- Do not infer exact historical measurement-to-tune association from file dates alone.
