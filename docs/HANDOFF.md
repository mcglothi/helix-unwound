# helixTune handoff

Last Updated: 2026-10-15
Status: ✅ Milestone 8 hardware-free demo and CI complete; hardware capture still pending
Current owner: none after this checkpoint; claim ownership in AIKB before editing
Branch: `pi/helixtune-foundation`

## Resume

1. Read this document and `AGENTS.md`; inspect `git status` and `git log -5 --oneline`.
2. Check AIKB active claims before editing. Only one agent edits this checkout at a time.
3. Continue the next task below. User authorized local checkpoint commits and, on 2026-10-15, the public GitHub repository and pushing completed current work. No release tagging or hardware claims.
4. Update this document and the AIKB index at the next complete milestone.

## Approved direction

- Product name: **Helix Unwound**. Tim's brand concept: a double helix unwinding at the top and evaporating into music notes, expressing freedom. See `docs/BRAND.md`. Internal package/CLI still `helixtune`.

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
- `cbd80f1`, `130087e`, `a7ff2ff`, `1b402ae` — milestone 3 corrections after Codex review: solver-input + trusted-target binding, default authentication outside `/api`, refused proposals stay open in the UI, atomic scene creation.
- `3495766` — milestone 4 (Codex): Measurements library, explicit capture-time identities/evidence, audited corrections, capture-context invalidation, and exclusion of unknown-baseline measurements from level anchors. A handoff-only commit follows this implementation checkpoint.

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

Corrections after Codex review (`cbd80f1`…`1b402ae`):
- Proposal context also binds a fingerprint of solver-consumed settings (role, hp/lp, EQ, gain, mute, routing) for every affected and contributing channel; names/presentation stay mergeable. Alignment binds driver identity of every measured channel.
- Solver targets are explicit: auto-EQ uses the target **shape** only; level proposals anchor to the predicted system from **trusted, non-overlapping** measurements (current provenance; single-channel and newest first). The exact target array is fingerprinted and recomputed at preview/apply. Without a trusted anchor, level proposals are refused with a reason. Untrusted measurements cannot change a solver target.
- Middleware authenticates **every** path except an explicit public surface (static UI shell/assets/manifest, POST `/api/session`); public endpoints must also be marked `@public_route`. Undecorated non-`/api` routes: anonymous 401, agent 403.
- UI keeps a refused proposal open with its conflict reasons; `canApply()` gates the button; frontend regression with a mocked 409.
- Scene files are created with `O_EXCL` (exactly one concurrent writer wins); owner overwrite uses temp + `os.replace`.
- Validation: **150 Python** passed locally; **125 passed / 25 skipped** from a clean archive; **20 frontend** tests; Svelte/TS 0/0; build OK; each commit's own suite passed at that commit. Every fix falsified (input check off, anchor trusting everything, old public-prefix rule, unconditional close, and the concurrency test failed before the fix).

Known holes after milestone 3:
- The missing owner measurement/provenance UI was addressed in milestone 4 below. Historical hardware is not inferred or silently replaced with today's drivers.
- The display system view now uses current, eligible, nonoverlapping captures (milestone 7); phase/model/capture-level limitations remain explicit.
- Agents can no longer delete wiring, so MCP can add but not rewire connections; owner canvas unaffected.
- Agents can edit roles/equipment specs that tighten limits; milestone 5 now distinguishes durable pending constraints from owner-confirmed sources.
- Measurement HTTP attestation requires explicit capture identities/evidence (milestone 4). Protection review now has separate individual value/unit/source bindings (milestone 5).
- Proposals remain in memory only (lost on restart).

Codex acceptance of corrective checkpoint:
- Reviewed the four corrective commits and reran **150 Python / 20 frontend tests**, with clean Svelte/TS checks. Accepted the five requested corrections: solver dependencies/trusted targets, default authentication outside the path prefix, retained UI conflicts, and exclusive scene creation.
- Agreed auto-EQ target shape does not need level anchoring because the fitter removes the level offset. Level matching requires a trustworthy reference and remains dependent on its actual contributing measurements/settings.
- Claude released ownership and Tim asked Codex to take the next stretch. No server restart, push, or hardware access.

## Milestone 4: explicit historical-aware measurement review

✅ COMPLETE (Codex)

- Added a Measurements navigation/view with capture date/source, output and seat tags, captured tune, hardware status, installed-vs-captured driver comparison, and owner review history. Historical/unidentified hardware is visibly separate from current hardware.
- Unknown captures start blank; reviewing today's installation is an explicit action, followed by evidence and owner confirmation. Manual historical rows keep independent identities. GB60 capture records remain historical against GS690 equipment; correcting a record requires an explicit flag and preserves old identities/reason.
- `POST /api/measurements/{id}/attest` is still owner-only and now **requires** explicit `drivers`, `reason`, and `expected_fingerprint`; a bare request returns 422. It cannot silently copy today's installation. Trusted in-process shorthand remains for existing local callers/tests and is not exposed over HTTP.
- Owner corrections and context invalidations append `driver_history`. Changing capture outputs, seat, or attached tune clears confirmation while preserving prior records; presentation-only edits do not. Metadata mutations/attestation/deletion share the engine lock. Measurement writes use temporary-file replacement.
- `GET /api/measurements` and `GET /api/measurements/{id}` return enriched metadata without raw arrays. The library can edit tags/details and attach or clear the capture-time tune. Changing these records never changes the active tune or installed equipment.
- Measurements without a known capture-time tune are excluded from solver level anchors, even when driver identities match. Owner evidence is not independent proof of historical truth; the UI deliberately does not offer a silent 'make eligible' operation.
- See `docs/MEASUREMENTS.md` for workflow and the attestation API change. Existing integration tests now declare synthetic capture identities rather than treating imported historical files as today's hardware by default.

Validation:
- **166 Python tests passed**, no skips with local private inputs. **141 passed / 25 skipped** from a clean archive without vendor inputs, backups, or built UI.
- **25 frontend tests passed**, including blank historical drafts, preserved identities, review/evidence requirements and explicit correction. Svelte/TS **0 errors, 0 warnings**; production build passed.
- Diff whitespace/staged credential checks passed. No user-state test, device connection, hardware writes, server restart, or push. Browser/phone rendered acceptance remains outstanding.
- The old Claude-launched server on :8765 still uses pre-milestone-2 Python against `~/.helixtune`. **Leave restart/migration to Tim's explicit call**, especially while protection provenance remains inferred. Test future changes with temporary state; do not use the existing server to validate this UI/API.

## Milestone 5: durable pending constraints and owner review

✅ COMPLETE (Codex; independent Claude review pending)

- `protections.json` version 2 stores individual pending/confirmed/cleared constraints with immutable source payloads and review history. Effective A–J output limits remain available to existing safety checks/API consumers.
- New metadata enforces immediately but cannot claim owner confirmation, even if an agent writes `manufacturer+confirmed` into source text. Only the owner review endpoint confirms exact records, with evidence and a fingerprint binding the current review state.
- Source value/unit/reference, driver ID/make/model/serial/assignment, or relevant role/policy changes invalidate confirmation. The prior limit remains enforced as pending; any replacement source starts pending. Presentation-only names/notes/positions remain mergeable. Returning old sources cannot restore confirmation.
- Clearing is per constraint, requires a reason and no attached device, and preserves history. Current sources must be corrected/removed first, so review cannot override live role/spec rules. Reintroducing a cleared source reactivates it as pending. The old bulk PUT/direct-engine replacement refuses operation rather than bypassing review.
- Version 1 aggregate limits migrate to pending legacy records with unknown original provenance, without rewriting tune bytes or lowering limits. Malformed/unsupported or source-fingerprint-corrupt protection state fails closed. Invalid numeric equipment metadata restores the last accepted design.
- Inspector now shows effective limits, pending counts, exact source records, changed/removed sources, individual confirmation/clearing, and review history. See `docs/PROTECTIONS.md` and updated `docs/ACCESS.md`.
- Known numerical semantics remain provisional: source unit strings are bound for review, not automatically converted. Known frequency specs must be recorded as Hz; slope as dB/oct. No proof of hardware behavior or speaker safety is implied.

Validation:
- **186 Python tests passed** locally; **161 passed / 25 skipped** from a clean staged Git archive without vendor files, personal backups or built UI. Includes 20 new synthetic provenance cases.
- **28 frontend tests passed**; Svelte/TS **0 errors, 0 warnings**; production build passed. Diff whitespace check clean.
- No hardware/device access (tests use emulator only), user-state testing, server restart/migration, push, or publication. Rendered browser/phone acceptance still outstanding. Leave the old :8765 server and `~/.helixtune` to Tim's explicit migration call.

## Milestone 6: revocable, expiring browser sessions

✅ COMPLETE (Codex; independent Claude review pending alongside milestone 5)

- Browser cookies now contain independent random `hs_` session IDs, never the permanent owner/agent credential. Only digests and monotonic expiry deadlines are kept in process memory; bearer authentication remains separate.
- Fixed 12-hour absolute expiry (activity does not extend it). Logout revokes the server record so copied cookies fail; repeated bootstrap replaces that browser's old record. Other browsers remain signed in. Server restart invalidates sessions while preserving role credentials.
- Thread-safe capacity of 64 concurrent sessions with expired-record pruning. Existing browser can replace its own slot at capacity; additional sign-ins return 429 rather than evicting another browser. HTTPS cookies are Secure; all session cookies are HttpOnly/SameSite=Strict/path `/` with Max-Age. Same-origin mutation checks remain enforced. Old raw-token cookies require sign-in after upgrade.
- Lost authentication returns the UI to sign-in, stops polling, and clears cached workstation state. Offline transport failures preserve the existing offline view. Sign-in can restart one polling loop; in-flight prior-generation polls cannot replace newly loaded tune state. No sign-in/expiry operation reconnects, disconnects or mutes hardware.
- See `docs/ACCESS.md`. Sessions are process-local; no multiworker deployment or phone pairing/session-management screen implemented.

Validation:
- **202 Python tests passed** locally; **177 passed / 25 skipped** from a clean Git archive without private inputs or built UI.
- **31 frontend tests passed**, including lost-authentication notification and offline distinction; Svelte/TS **0 errors, 0 warnings**, production build passed.
- Real authenticated API regressions cover cookie/bearer separation, copied-cookie revocation, expiry boundary/activity, restart, independent browsers, rebootstrap, Origin failures, HTTPS attributes, capacity and concurrent sign-ins. All state temporary; no server restart, user data migration, hardware use, push or publication. Rendered acceptance remains outstanding.

## Milestone 7: evidence-aware acoustic estimates

✅ COMPLETE (Codex; independent review pending)

- Main/Drive graphs, proposal previews and solver level anchors now select the same current hardware/known-tune captures, preferring isolated then newest records and refusing overlaps. Unknown/stale records remain available as historical measured data but cannot project onto current drivers or shift the display target.
- Responses include contributor IDs/fingerprints/bandwidths, exclusions with reasons, coverage and missing active outputs, aggregation method and explicit magnitude-model limitations. No eligible data produces null estimates/target. Partial coverage stays visible instead of double-counting an overlapping combined capture.
- Master gain delta is applied once outside channel transfer clipping, for both isolated and combined predictions. Captured traces remain unchanged; target level follows the selected predicted 300 Hz–3 kHz reference, not independently verified SPL.
- Combined captures are not duplicated into individual output curves; mixed-role captures are grouped as mixed. Role group labels follow the proposed/current tune. Input-routing changes, captured muted outputs, invalid data and combined-capture delay/polarity changes refuse projection and assisted-tuning use.
- Proposal inputs now bind delay/polarity as these settings affect combined-capture eligibility; synthetic regressions verify preview AND apply refuse after a contributing output changes them.
- UI labels estimates and power sums explicitly, with expandable source/assumption details in Studio/Drive. The empty state directs owners to measurement review. See `docs/PREDICTION.md` and updated MCP docs.
- Known model limits remain: phase-blind power addition, approximate electrical power-ratio scaling of combined captures, numerical filter/mute floors, edge-value extension outside capture bandwidth, and unverified recording/playback level comparability. No absolute SPL, speaker safety, or physical crossover alignment claim.

Validation:
- **217 Python tests passed** locally; **192 passed / 25 skipped** from a clean Git archive without private inputs or built UI. Includes 15 synthetic prediction regressions.
- **34 frontend tests passed**; Svelte/TS **0 errors, 0 warnings**; production build passed. Diff whitespace check clean.
- Hardware/user state/existing :8765 server untouched. Public repository and pushes were explicitly authorized by Tim, including the **Helix Unwound** name. Initial main includes session/protection work and branding brief; milestone 7 is pushed on the collaboration branch for review.

## Milestone 8: hardware-free demo and portable CI

✅ COMPLETE (Codex; first hosted CI run green)

- `helixtune demo` runs on loopback port 8770 with separate `~/.helixtune-demo` state, invented parameter addresses, a valid virtual three-way/subwoofer tune, a baseline scene and eight explicitly synthetic captures. No vendor map or private inputs are required. Same auth, proposals, protections and history paths as the normal workstation.
- Existing non-demo directories are refused unchanged. Incomplete/future demo initialization fails closed; restarting an existing demo preserves edits/deletions instead of reseeding. A normal hardware engine refuses demo state. Demo inventory has fictional identities and no personal microphone serials.
- API refuses physical connections before opening ports or detaching a working emulator; demo port listing does not enumerate hardware. Engine also requires an actual in-memory emulator transport instead of trusting a caller's kind label. Owner/agent capabilities remain enforced.
- Visible demo banner and Helix Unwound wordmark/sign-in/tab/manifest names. See `docs/DEMO.md` and README for launch commands.
- GitHub CI: Python 3.11/3.13 on Linux/macOS; frontend checks/tests/build; wheel checks and an isolated installed-wheel demo/API smoke. Actions pinned to verified release SHAs, read-only repository permission, locked dependencies. Main pushes and PRs trigger checks; no release publishing.
- Packaging fix: Hatch previously omitted Git-ignored built frontend files. Wheel artifacts now explicitly include the Svelte build when present, while source installation/build without generated UI continues working. Built UI, vendor files, user data and credentials remain excluded from Git.

Validation:
- **227 Python tests passed** locally; **202 passed / 25 skipped** from a clean Git archive without private inputs/generated UI. Ten new synthetic demo cases cover isolation, durable edits, guards, CLI startup and authentication.
- **34 frontend tests**, Svelte/TS **0 errors/0 warnings**, production build. Wheel built with and without UI; built wheel's isolated demo/API smoke passed.
- First hosted run **38831378358 passed all five jobs**, including both Python versions on both OSes and frontend/packaging. Follow-up run **38831607646 also passed all five jobs**, including the isolated installed-wheel demo/API smoke.
- Native Brave desktop review on temporary port 8779 verified rendered Studio/banner, Auto-EQ preview, Apply (two bands), and Undo (zero bands). Additional browser actions stopped when the user changed browser state. This is limited desktop acceptance; phone/tablet, session sign-out/expiry and protection-review rendered coverage remain pending.
- Temporary demo process on :8779 uses `/tmp/helix-unwound-demo-review-20261015`; it is independent of the old :8765 server and `~/.helixtune`. No physical hardware, user state migration or firmware access. Public branch pushed under Tim's authorization.

## Next tasks

1. **Review milestone 5:** Claude should independently inspect provenance retention, source bindings, per-constraint clearing/reappearance, version 1 migration, and the owner UI. Do not edit concurrently; claim this checkout first. Current-source clearing deliberately requires correcting/removing its metadata, preserving the earlier rule that live role/spec constraints still apply.
2. **Review milestone 6:** independently inspect session lifecycle and UI reauthentication. Phone pairing should mint these sessions; device/session management and multiworker hosting are still future work.
3. **Review milestone 7:** independently verify evidence selection, master gain, combined-capture attribution, proposal eligibility binding and explanatory UI. Portable CI is now implemented (milestone 8); settle a license before inviting community code contributions.
4. Verify hardware protocol from Windows captures (overrides this order as soon as captures exist) before live writes: addresses, coefficient sign, fixed-point format, delay/mute/routing semantics, ACK validation, safeload/atomic updates, readback and reconnect behavior.
5. Continue rendered desktop/phone acceptance of sign-in, sign-out, and physical-output configuration using the demo; short-lived phone pairing and per-device sessions remain future work. Persistent protection tightening is deliberately conservative; don't reintroduce metadata-based relaxation.

Work while hardware captures are pending: add a **Svelte device connection/recovery panel**
(currently only API/legacy UI exposes connection actions; verify workflows against
the emulator without claiming hardware semantics), then **read-only REW integration**
(connect/discover capabilities, import measurement data with provenance, no automated
sweeps or channel switching), then saved-state transaction/recovery improvements,
responsive/keyboard acceptance and a guided first-run flow. Argon's longer-term
adaptive/embedded roadmap was reviewed; no USB/HID rewrite, native sweep engine,
CAN adaptation or autonomous hardware writes were adopted from it.

These are review recommendations, not approval for every proposed product feature. See `docs/DESIGN.md` for prior choices and compare against implementation; design docs contain aspirational/unverified claims.

## Reproduction and validation

- `uv sync`; Python tests: `uv run pytest -q`.
- `cd web && npm ci && npm run check && npm test && npm run build`.
- `uv run helixtune serve` serves built Svelte UI when available; use a temporary `--data` directory for experiments.
- Local private inputs: ignored `artifacts/extracted/app/deviceFiles/DSPPro2.at01` and ignored `captures/backups-2018/`. Some original tests skip when these are missing. New foundation regressions must remain runnable without them.
- Public GitHub repository: https://github.com/mcglothi/helix-unwound (Tim authorized public creation/push on 2026-10-15). Initial default `main` and collaboration branch were pushed; subsequent feature work remains on the collaboration branch for review.

## Known limits at handoff

- No protocol/hardware verification yet. Emulator and engine share provisional assumptions.
- “Synchronized” only means all write requests returned responses accepted by the current client. ACK content, atomicity, safeload, and readback remain unverified; this is not a hardware-verified tune.
- No automatic device mute or rollback is attempted after transport failure. Uncertainty can include partially applied filters. User must review and deliberately resynchronize.
- The network API now enforces owner/agent capabilities, but same-user local processes that can read owner files can assume owner authority. Direct engine/CLI operations are trusted local operations; this is not an OS sandbox.
- Aggregate filter headroom, safe power/excursion, and prediction-display issues remain open. Proposal conflict protection is implemented, but future solver dependencies must be added to its binding. These milestones do not establish speaker protection or public-release readiness.
- API/MCP role credentials remain long-lived; browser sessions now expire and revoke independently. Per-agent identities and browser-session management are not implemented. HTTP is unencrypted; use trusted networking/encrypted tunnels for remote access. See `docs/ACCESS.md` for rotation and remaining pairing work.
- Stricter protection floors are persisted before writes; they may remain after a failed tune update. Individual offline owner clearing of obsolete constraints is the only supported relaxation path.
- Tune/system persistence still uses direct file writes (protection and measurement records use replacement); crash-safe storage and full history reconstruction remain future work.
- UI was source-reviewed; Codex could not inspect a rendered browser session in this environment.
- Current event summaries cannot reconstruct a full tune timeline after restart.
- Legacy preset crossover/mute/delay interpretation remains provisional.
- Do not infer exact historical measurement-to-tune association from file dates alone.
