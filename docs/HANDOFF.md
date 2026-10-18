# helixTune handoff

Last Updated: 2026-10-18
Status: ⚠️ Live hardware test done 2026-10-18 (session-based stored backup, first supervised write; see HARDWARE-EVIDENCE); session/backup fixes and Director-volume guard await Codex review; physical engine sessions still disabled
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
- Studio Console visual direction, consistent themes, Drive/Setup/System views, phone/tablet/desktop support, foldables considered. Tim explicitly prioritizes polished modern UI/UX and research into community tuning methods AND complaints about DSP software; record concrete acceptance criteria, not only technical ideas.
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

## Milestone 9: connection workflow, read-only REW and usability evidence

✅ COMPLETE (Codex; independent review pending)

- Header connection status opens a responsive Connection & recovery dialog with human-readable states, explicit port selection, read-only default, optional write permission, disconnection and reviewed full-send/recovery. Reconnecting resets write permission; connecting never auto-imports or overwrites a device tune. Technical send detail is progressively disclosed.
- Review binds tune + connection generation + server boot nonce. UI sends that context with typed OVERWRITE confirmation. Backend rechecks under lock and refuses after tune change, reconnect or process replacement before any writes. Existing trusted API callers can still use the older explicit-confirm request without context. Actual hardware readback remains unverified.
- Serial replacement is serialized and disconnection closes owned transports, including error cleanup. Concurrent fake-serial regression verifies superseded connections are closed. Demo transport guards remain intact.
- Owner-only local REW discovery/preview/import (including GET capability boundary) issues only fixed loopback GET endpoints, with timeout/response limits, proxy/redirect refusal and documented big-endian float decoding. Handles log/linear axes (DC omitted), list/index-keyed collections, duplicate UUID refusal, source-change checks and local idempotent copy. No sweeps, audio capture, settings changes, subscriptions or writes to REW.
- Measurement imports preserve source summary/date text/smoothing/content fingerprint/phase in provenance; unknown physical drivers, timezone and capture-time tune remain unknown unless the owner explicitly selects a scene. No inference from today's hardware. UI previews source bandwidth/data before copying; source details are expandable. See `docs/REW.md`.
- Usability work: themed modal border/backdrop, outcome-focused labels, bounded capture-list scrolling, imported-result focus/scroll to its heading, readable validation errors and separate offline/ready/write/recovery states. Full product/accessibility/mobile acceptance is still open.
- `docs/research/COMMUNITY-UX.md` captures Tim's ongoing research requirement and first source-backed observations with acceptance criteria. Searched DIYMobileAudio/CarAudio.com and firsthand r/CarAV reports. DIYMA direct fetch failed and is explicitly an unread lead; do not claim a consensus or infer a technical rule from it. Review preferences and implementation decisions remain separate.

Validation:
- **255 Python tests passed** locally; **230 passed / 25 skipped** from a clean archive without private inputs/generated UI. **37 frontend tests**, clean Svelte/TS **0 errors/0 warnings**, build passed.
- Native Brave review at temporary :8780: emulator read-only connect → disconnect → explicitly write-enabled connect → review → type confirmation → send → writes-active → disconnect. REW browser → preview → import used a generated HTTP fixture at :48735, with no physical REW/audio/DSP activity. Imported copy visibly kept unknown outputs/hardware/tune. Fixture service stopped after testing; no live REW compatibility claim.
- Isolated temporary state `/tmp/helix-unwound-connections-review`; old :8765 user server/data untouched. Temporary demo :8779 from milestone 8 may also remain running. Public branch/PR1 updated; no main merge/release/firmware/hardware use.

## Milestone 10: recoverable sessions and useful Setup guidance

✅ COMPLETE (Codex; independent Claude review pending)

- Versioned atomic `workstation.json` saves the accepted tune, bounded Undo/Redo history and A/B slots; the previous validated checkpoint provides recovery with a visible notice. Both unreadable refuses startup rather than substituting defaults; future versions refuse downgrade. Legacy `current.json` migrates only on the first save and becomes a compatibility export. See `docs/SESSION-RECOVERY.md` for scope and limitations.
- Restart always remains disconnected without writes or a baseline. Output protections stay independently enforced. Failed device edits/Undo/Redo/scene/A-B operations preserve the prior checkpoint and accepted state.
- Save failures after accepted device writes retain the new tune in memory with a persistent warning and owner retry action. Compatibility-export failures are distinguished. Event-log I/O failure no longer turns an accepted tune change into a misleading rejected request.
- Redo added to engine, authenticated HTTP API, MCP and header. A new edit/scene/A-B switch discards redo. Scene/A-B history now enters the checkpoint as part of the final state rather than after saving.
- Setup starts with scene/connection/measurement actions and live eligibility counts. Navigation no longer gives false completed-step checkmarks. Electrical cutoff comparisons no longer claim acoustic alignment. The sidebar explains review/remeasure instead of advertising future AI features.
- Native Brave acceptance on isolated synthetic demo port **8781** verified edit → Undo → Redo, rendered Setup checklist and an actual process restart retaining the edited mute state and Undo depth. No real DSP, REW or `~/.helixtune` accessed; phone/tablet and full keyboard acceptance remain open.
- Storage smoke timing: one 200-step checkpoint (default ten-output tunes) was ~4.54 MB / 0.116 s on this Mac after compact serialization. This is not a performance guarantee; large-history responsiveness and independently managed equipment/measurement transactions remain future work.

Validation: **272 Python tests passed** locally; **247 passed / 25 skipped** from a clean staged Git archive without private inputs or built UI. **37 frontend tests**, Svelte/TS **0 errors/warnings**, production build passed. New synthetic persistence regressions cover restart, backup/malformed/future files, legacy adoption, save failure/retry, redo protections and device failure.

## Milestone 11: output setup and keyboard/mobile navigation

✅ COMPLETE (Codex; independent Claude review pending)

- Setup's physical A–J output map shows routes, roles, tune mute state, recorded drivers, filters, independent output limits and pending reviews. Per-output name/role/route drafts have an exact before/after review and explicit workstation/live final action. Custom mixes remain intact unless deliberately replaced. See `docs/OUTPUT-SETUP.md`.
- Owner-only setup PUT binds to output settings, equipment, policy/protection and device/boot context under the engine lock. Stale reviews refuse with 409, unrelated outputs remain mergeable, and validation/protections/Undo/recovery reuse existing engine paths. Invalid model errors now serialize without non-JSON exception context.
- **Routing correction:** the original all-empty-mix legacy heuristic could silently restore L/R routes after switching the last active input Off. Legacy defaults now apply only when every serialized channel omits `mix`, keyed by physical ID. Explicit all-Off routes survive validation/save/restart/Undo. No physical hardware accessed.
- Cmd/Ctrl Undo/Redo, bracket output navigation, discoverable Keys help, typing/modal/composition guards, skip link, Studio selector above the graph and focusable jump to controls. Main landmarks are no longer nested in Setup/Measurements.
- Narrow-screen header is compact and nonsticky; corrected the measurement-count hiding rule. Output cards/dialogs adapt without relying on branding assets. Review/back navigation explicitly restores useful keyboard focus.
- Native Brave isolated demo8782 verified name edit → exact review → save → keyboard Undo/Redo. Responsive **390px viewport emulation** verified Jump to controls focus/visibility and output editor/review/cancel. DevTools closed afterward; physical phone/touch, screen-reader and foldable acceptance remain open. Old real-data server untouched.
- Tim is coordinating repo graphics/logo ideas externally with Gemini; no branding assets modified in this milestone.

Validation: **287 Python tests passed** locally; **262 passed / 25 skipped** from a clean staged Git archive without private inputs or built UI. **43 frontend tests**, Svelte/TS **0 errors/warnings**, production build passed. Fifteen new synthetic API/model cases and six frontend helper cases cover stale edits, permissions, safety, live-write failure, custom routing, all-Off persistence and keyboard guards.

## PC-Tool preset evidence follow-up (2026-10-17)

✅ COMPLETE (Codex corrections following Claude's demo-mode review)

- Claude loaded two existing presets in PC-Tool 4.80b Demo Mode on the capture laptop, without DSP hardware; local evidence is in `../win11-capture/preset-ground-truth/FINDINGS.md` and screenshots. This validates observed preset/UI relationships, not USB write/readback behavior.
- Corrected the missing `F Sum` label at CN12 and terminal `Subwoofer R`; CN25/26 now name Subwoofer 1/2. Invalid negative codes no longer index the end of the label table. Existing role inference remains unchanged.
- Unknown `<T P>` values are reported as preset parameters, without degree units or claims that they are the displayed phase. They remain unapplied. Delay's sample interpretation is annotated with the demo comparison; no crossover-family heuristic or hardware protocol was changed.
- Checked both local preset XMLs: active crossover slope is `G=-24`; neither has a `dB` attribute. Sent this terminology clarification back to Claude for the evidence notes.
- **302 Python tests passed** locally; 15 new portable synthetic cases cover label boundaries, unknown codes, delay conversion and unknown-P reporting. No private XML, screenshots, binaries or user state committed. Physical USB captures remain the next source of hardware evidence.

## First real USB capture reconciliation (2026-10-17)

✅ Checkpoint complete; **physical application writes disabled** pending remaining validation

- Claude supplied real PC-Tool↔DSP capture findings; local source `../win11-capture/captures-2026-10-17-FINDINGS.md`. Private captures/presets/maps remain ignored. Codex made no hardware connection and did not restart the old real-data server.
- Corrected parameter command to `03 00 01 addr16 + words`, strict command/bank/address/channel ACK matching, identify payload174/frame179 and sync burst. Removed guessed RAM-read command; preset opcodes04/05 always refuse. Physical client transactions are identify-only, engine/API deny physical write enable, UI exposes emulator writes only. No override added.
- Renderer now reserves HP0..2/FO1 and LP3..5/FO2, stage6 identity. Mapping uses captured .707 for two-pole Butterworth kernels; generic math remains ideal. Unsupported larger per-filter banks refuse rather than repack. Quantization and other slope/session/master/routing semantics remain open.
- Offline audit reconstructed **93 writes / 93 ACKs across30 local capture files**. HP70 LR24, HP70 LR12 and LP400 LR24 matched rendered words within1LSB (18 words each). No byte-exact/generalized hardware compatibility claim.
- Stored preset XML readback discovered by capture tooling is **stored state, not arbitrary live RAM readback**. Newer stored preset differs from old backups. No preset read/select/store feature enabled by this checkpoint. See `docs/HARDWARE-EVIDENCE.md`.
- Validation: **331 Python tests** locally (29 new portable capture-structure/quarantine/layout regressions); frontend43, Svelte/TS0 errors/warnings and production build. **306 passed / 25 skipped** from a clean staged Git archive. Old running versions must not use hardware writes.

## Step 1: read-only stored-preset backup (2026-10-17)

⚠️ Implementation ready; **live Mac/DSP validation pending Tim**

- Claude independently approved the prior protocol corrections: 143/143 replayed words within1LSB, 109 exact; falsification with ideal Q failed the expected LR24 cases. He reported the old real-data server stopped with Tim approval. Codex did not stop/restart it.
- Added exact read allow-list: identify and bounded32/03 stored-memory reads only. Session09, baud0A, slot selection32/01, names32/07, other probes and all physical writes remain blocked. No automatic connection or fallback. Read-only at19200 may not work without a session; this is deliberately left for the live test.
- Raw frame audit corrected a summary omission: zero-filled request body is NN for name / NN+1 for data, and data replies add a zero trailer. Private replay now checks real request sizes and response frames, not only reconstructed memory.
- Bounded qCompress/zlib/XML parsing, per-reply bank/address/count/channel checks, two matching reads, complete mode0600/no-overwrite backup files and separate blob/XML hashes. Captured stored memory replays to byte-identical XML; no claim of live RAM or selected-slot backup.
- Explicit `backup-stored --port ... --output ...` CLI, owner-only API backup/download and separate copy-to-new-scene workflow. No automatic adoption, overwrite, baseline or protection change. UI backup/import warnings remain visible.
- Native Brave synthetic transport acceptance verified backup, download link and copy-to-scene; active tune and Undo remained unchanged. Test server/tab closed. No real serial port opened or real user state used.
- Validation: **366 Python tests** locally, including35 new backup cases (one optional private replay); frontend43, Svelte/TS0 errors/warnings and build passed. **340 passed / 26 skipped** from a clean staged Git archive. See `docs/STORED-PRESET-BACKUP.md` for live acceptance instructions and limits.

## Claude checkpoints after the captures (2026-10-17)

✅ Reviewed by Codex (read-only); published with Tim's approval.

- `c421d70` — PC-Tool 8.24 quantization truncates toward zero (143/143 captured words bit-exact;
  round 109); `.afpx` `LG` link groups imported; channel/band/crossover/EQ-reset edits copy the
  edited item to linked channels (delay/name/role/routing per channel; `?link=false`); UI badge
  and Unlink; Drive nudges stay per channel. Codex: no blockers.
- `2e24b34` — capture-faithful emulator: identify layout (unit code zeroed), `02` echo, `1b`
  status, silent `09`, `32 03` stored reads, erased flash `0xFF`. Codex: no blockers.
- `94c8506` + `53ed071` — red/yellow/green high-pass tiers: the Fs-multiple margin is advisory
  only beside a manufacturer minimum of the identical recorded driver; `fs_unbounded` keeps it
  enforced for any driver on the output without one; import/status/check return advisories.
  Codex found the id-only pairing and missing import advisories; both fixed and approved.
- `ee6dc2e` + `78c5987` — session layer (emulator-only): captured open (baud recovery, identify,
  `09 01`, high speed), keep-alive pinger under `serve`, close on detach. Codex found baseline
  retention after a missed echo and identify-before-recovery; both fixed and approved. A missed
  keep-alive now invalidates the baseline and pauses incremental writes until reconnect + a
  confirmed full overwrite.

Validation at `78c5987`: 398 Python (private capture comparisons ran locally), frontend 43,
Svelte/TS 0 errors, production build. Each fix was falsified by reverting it.

Before any physical session is enabled: (1) `Client.drain`'s deadline cannot interrupt a single
blocking `transport.read`, so bound the serial read timeout too; (2) after a heartbeat failure,
require reconnect to restart monitoring (the UI message already says so; enforce it); (3) handle
partial-open/close failures on hardware. Physical transports still reject every session byte.

## Next tasks

1. **After the 2026-10-18 live test:** stored backup now opens PC-Tool's session and sends
   `32 01 06 00` (the only way the DSP answered `32 03`); `Session` pauses 0.1 s after each sync;
   writes to Director volume parameters are refused. Pre-session hardening done (2026-10-18):
   physical ports must have a read timeout <= 0.1 s; a missed keep-alive sets `needs_reconnect`
   and refuses every write, full overwrites included, until reconnect; a partial `Session.open`
   closes itself (once) before raising, and an unrecognised device gets nothing after identify.
   Physical write sessions exist only behind `serve --allow-physical-writes` (Tim approved
   2026-10-18; off by default). With it, a write-enabled serial connection may carry identify,
   bounded stored reads, PC-Tool's session/keep-alive, `32 01 06 00` and `03` writes only.
   `04`/`05`/`13`/`17`/`1b` and other `32` commands stay refused, and the Director-volume guard
   and reconnect rule apply. Before any `03` byte, unverified settings are refused
   (`mapping.physical_problems`) and the provisional master is excluded from the physical image
   and baseline. The UI enables the write checkbox for serial ports only when the server reports
   `physical_writes_allowed`; the existing context-bound review + typed OVERWRITE is the
   first-write confirmation and shows port, exclusions, refusals and live consequences.
   While a real DSP is attached, master gain is workstation-only: `status.master_on_device` is
   false, predictions leave master changes out (with a stated limitation), and the Drive view
   labels and disables the master tile. First used on hardware 2026-10-18: full overwrite
   plus EQ/mute/gain edits, all acknowledged (see HARDWARE-EVIDENCE). Refused changes now show a
   persistent "Not applied" panel in every view and edited fields snap back; unmuting an output
   with positive gain offers a reviewed, atomic "Unmute at 0 dB" (POST /api/channels/{cid}/unmute-at-zero,
   stale review refused, never raises gain). Inspector EQ/crossover fields are labelled. Start/end every truck test by reading the
   Director's Digital Volume.
2. **Review milestone 5:** Claude should independently inspect provenance retention, source bindings, per-constraint clearing/reappearance, version 1 migration, and the owner UI. Do not edit concurrently; claim this checkout first. Current-source clearing deliberately requires correcting/removing its metadata, preserving the earlier rule that live role/spec constraints still apply.
3. **Review milestone 6:** independently inspect session lifecycle and UI reauthentication. Phone pairing should mint these sessions; device/session management and multiworker hosting are still future work.
4. **Review milestone 7:** independently verify evidence selection, master gain, combined-capture attribution, proposal eligibility binding and explanatory UI. Portable CI is now implemented (milestone 8); settle a license before inviting community code contributions.
5. Hardware protocol: framing, write command, EQ/crossover/delay/gain/mute/invert addresses and maths, quantization, link groups and the session sequence are confirmed by the 2026-10-17 captures. 6/18 dB first-order slopes and BW12 (Q 0.71) are bit-exact as of capture 23. Routing now targets MAINMATRIX like PC-Tool (captures 24a/b). Still open before enabling them: Bessel and LR36 constants, master gain semantics, Save&Store/flash. Director controls never cross USB.
6. Continue rendered desktop/phone acceptance of sign-in, sign-out, and physical-output configuration using the demo; short-lived phone pairing and per-device sessions remain future work. Persistent protection tightening is deliberately conservative; don't reintroduce metadata-based relaxation.

Work while hardware captures are pending: next measurement capture planning/verification
guidance, then broader physical-phone/keyboard/accessibility acceptance. Continue community UI/UX research and test live REW
compatibility when available; the new adapter currently has fixture acceptance. Argon's longer-term
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

- USB captures verify framing, commands and selected filter cases; the session and one supervised gain write were validated live (2026-10-18) with one-off scripts. Engine physical writes exist only behind `serve --allow-physical-writes`, limited to capture-verified settings with the provisional master excluded, and have not yet been used on hardware. See HARDWARE-EVIDENCE.md.
- “Synchronized” only means all write requests returned responses accepted by the current client. Parameter echo ACK content is now checked; atomicity, safeload and independent readback remain unverified; this is not a hardware-verified tune.
- No automatic device mute or rollback is attempted after transport failure. Uncertainty can include partially applied filters. User must review and deliberately resynchronize.
- The network API now enforces owner/agent capabilities, but same-user local processes that can read owner files can assume owner authority. Direct engine/CLI operations are trusted local operations; this is not an OS sandbox.
- Aggregate filter headroom, safe power/excursion, and prediction-display issues remain open. Proposal conflict protection is implemented, but future solver dependencies must be added to its binding. These milestones do not establish speaker protection or public-release readiness.
- API/MCP role credentials remain long-lived; browser sessions now expire and revoke independently. Per-agent identities and browser-session management are not implemented. HTTP is unencrypted; use trusted networking/encrypted tunnels for remote access. See `docs/ACCESS.md` for rotation and remaining pairing work.
- Stricter protection floors are persisted before writes; they may remain after a failed tune update. Individual offline owner clearing of obsolete constraints is the only supported relaxation path.
- Tune/Undo/Redo/A-B use recoverable atomic checkpoints; system/design/target writes and cross-file transaction boundaries remain independent. Full activity-timeline reconstruction and multi-process data-directory locking remain future work.
- Isolated native Brave demo acceptance covers selected desktop flows; full phone/tablet, keyboard and accessibility review remains pending.
- Current event summaries cannot reconstruct a full tune timeline after restart.
- Legacy preset crossover/mute/delay interpretation remains provisional.
- Do not infer exact historical measurement-to-tune association from file dates alone.
