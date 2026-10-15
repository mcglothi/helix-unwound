# helixTune handoff

Last Updated: 2026-10-16
Status: ✅ Foundation milestones 1–3 complete (3 = proposal binding + route capabilities, by Claude); awaiting Codex review
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
- `7f2636d` — foundation milestone 2: persisted physical-output protection floors, authenticated owner/agent capabilities, owner sign-in/open command, offline protection editor, and regression coverage. A handoff-only commit follows; use `git log` for the tip.
- `39aed64` — milestone 3A (Claude): proposals bound to field before-values and context (target, measurements, driver identity); measurement driver provenance with owner attestation; stale/unknown measurements refused for optimisation.
- `6dd81aa` — milestone 3B (Claude): route-declared capabilities (agent writes opt-in via `@agent_allowed`, new routes owner-only), owner-only deletions/attestation, no silent scene overwrites.

## Milestone 1: device writes and physical channel identity

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

## Milestone 2: physical protection and authenticated capabilities

✅ COMPLETE

- `protections.json` version 1 lives outside tune/snapshot state. Startup migrates current roles + equipment without rewriting the tune. Accepted metadata can tighten saved floors; changing roles to unused, muting, deleting specs/equipment, and restoring old scenes cannot weaken them.
- Every adoption path checks persistent limits: ordinary edit/replacement, undo, snapshots, A/B, proposals, and full push. Gain/EQ ceilings also apply to unused outputs.
- Owner-only `PUT /api/protections/{cid}` requires no device attached and explicit `RECONFIGURE`. The Inspector exposes the same operation; current role/spec constraints are reapplied. Invalid equipment constraints restore the last accepted system design instead of poisoning saved startup state.
- Owner/agent bearer credentials are created under the data directory's `auth/` with 0700 directory / 0600 files. API reads and writes require authentication; source headers are audit labels only. Agent credentials cannot connect/disconnect devices, full-push, or change protections. They remain tuning-editor credentials, not proposal-only.
- Browser bootstrap: run `helixtune open` after `serve`, with matching `--data`/`--port`. It opens loopback with a fragment credential, removed before API calls, and exchanges it for an HttpOnly SameSite=Strict owner cookie. Cookie mutations require a same-origin Origin header. Sign out clears the browser session.
- MCP reads only the agent credential by default (`HELIXTUNE_DATA_DIR`, optional `HELIXTUNE_TOKEN`); overview reads now use the same authenticated/error-aware helper. Explicit crossover bypass now sends JSON null and is protection-checked; empty requests are rejected.
- Follow `docs/ACCESS.md` for migration, scopes, and offline reconfiguration. There is no production test/auth bypass.

Validation at milestone 2:

- **127 Python tests passed** (no skips with local private inputs).
- **17 frontend tests passed**, including fragment removal and session exchange regressions; Svelte/TS **0 errors, 0 warnings**; production build passed.
- **63 portable foundation tests passed from a clean Git archive**, with no vendor files, private backups, or built UI. These include the original 25 synthetic tests plus 38 protection/access regressions.
- Diff whitespace check and staged credential-pattern scan passed. No device connected by Codex; all tests use isolated temporary state.
- Claude's existing development server is still running pre-change Python code and was **not restarted**. Restart it before reviewing the new frontend/API together, then run `helixtune open`. Do not auto-reconnect hardware. Rebuilt assets are local/ignored.

## Milestone 3: proposal binding and route-declared capabilities

✅ COMPLETE (Claude, reviewed scope agreed with Codex in AIKB IM thread `helixtune-foundation-review-20261015`)

A — proposal conflicts (`39aed64`):
- `Proposal.context` = seat, target fingerprint, `{measurement id: content fingerprint}`, `{channel: driver-identity fingerprint}`. Every edit carries `before`; comparison normalises models/enums through JSON.
- `Engine.proposal_conflicts` runs under the engine lock in both preview and apply. Conflict → `ProposalConflict` → HTTP 409 `{"error":"conflict","conflicts":[...]}`; accepted tune and stored proposal unchanged. The global revision is not used, so presentation changes and unrelated edits still merge.
- Measurements gained `drivers` (channel → [{id, make, model}]) and `drivers_source`. `None` = unknown provenance (all legacy imports). Optimisation (auto-EQ, levels) refuses unknown or stale measurements with reasons in proposal notes. Owner-only `POST /api/measurements/{id}/attest` records the current design's drivers for that measurement. Import never infers provenance.
- UI: ProposalCard shows conflicts and disables Apply; preview re-validates on every engine revision. MCP docs explain 409 conflicts and refusals.

B — capabilities (`6dd81aa`):
- Middleware authenticates only; `authorize_route` (app-wide dependency, after routing) refuses agents on mutating routes without `@agent_allowed`. Regression registers an undecorated route at test time → agent 403.
- Owner-only: all DELETEs except proposal discard, attestation, device, protections, session. Scene save / preset import with an existing name → 409 `exists` for everyone; only owner may pass `overwrite: true`; owner UI confirms first.

Validation at milestone 3:
- **140 Python tests passed** locally (private inputs present). **115 passed, 25 skipped** from a clean `git archive` (no vendor files, backups, or built UI).
- **17 frontend tests passed**; Svelte/TS **0 errors, 0 warnings**; build passed. `git diff --check` clean.
- Falsified: removing the field-conflict check fails 2 conflict tests; disabling the route capability check fails 2 capability tests. No hardware, no server restart, no user state used.

Known holes after milestone 3:
- No owner UI to list measurements or attest provenance yet; until then Tim's 2018 measurements are refused for auto-EQ (only API attestation exists).
- Target level-matching (`_target_on_grid` via `system_view`) still uses every seat measurement, including stale/unknown ones (prediction-honesty milestone).
- Agents can no longer delete wiring, so MCP can add but not rewire connections; owner canvas unaffected.
- Agents can still edit roles/equipment specs that tighten persistent floors (protection-provenance milestone).
- Attestation snapshots the whole current design for a measurement's channels; it does not yet bind individual spec values (needed for protection attestations, not measurement provenance).
- Proposals remain in memory only (lost on restart).

## Next tasks

1. **Next — protection provenance (design review first).** Two tiers agreed in IM: new constraints enforce immediately; persistence as a physical floor requires an owner attestation bound to exact values/units/output/driver/source revision. Pending constraints persist outside snapshots and survive restart, source deletion and metadata change until the owner explicitly clears them (per constraint, with reason). If an attested source later changes, the attestation is void and the old value stays enforced as pending. Keep the offline (disconnect) interlock for relaxation; software disconnect does not silence the DSP; design a write-paused maintenance state only after captures prove mute/ACK.
2. **Auth follow-up before wider remote use:** random server-side session ids with expiry and revocation on logout instead of the raw owner token in the cookie; reject bearer tokens in the cookie slot; keep Origin checks; tests for expired/revoked/restarted sessions. Phone pairing should mint such sessions.
3. Prediction integrity: master gain omitted, overlapping measurements double-counted, phase-blind sums cannot establish crossover alignment. Make limitations visible and preserve measurement provenance.
4. Verify hardware protocol from Windows captures (overrides this order as soon as captures exist) before live writes: addresses, coefficient sign, fixed-point format, delay/mute/routing semantics, ACK validation, safeload/atomic updates, readback and reconnect behavior.
5. Rendered browser/phone acceptance of sign-in, sign-out, and physical-output configuration; short-lived phone pairing and per-device sessions remain future work. Persistent protection tightening is deliberately conservative; don't reintroduce metadata-based relaxation.

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
- The network API now enforces owner/agent capabilities, but same-user local processes that can read owner files can assume owner authority. Direct engine/CLI operations are trusted local operations; this is not an OS sandbox.
- Aggregate filter headroom, safe power/excursion, stale proposals, and prediction issues remain open. These milestones do not establish speaker protection or public-release readiness.
- Auth uses long-lived role credentials, not per-agent identities or expiring sessions. HTTP is unencrypted; use trusted networking/encrypted tunnels for remote access. See `docs/ACCESS.md` for rotation and remaining pairing work.
- Stricter protection floors are persisted before writes; they may remain after a failed tune update. Deliberate offline owner reconfiguration is the only supported relaxation path.
- Current state persistence uses direct file writes; crash-safe storage and full history reconstruction remain future work.
- UI was source-reviewed; Codex could not inspect a rendered browser session in this environment.
- Current event summaries cannot reconstruct a full tune timeline after restart.
- Legacy preset crossover/mute/delay interpretation remains provisional.
- Do not infer exact historical measurement-to-tune association from file dates alone.
