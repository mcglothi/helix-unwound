# helixTune collaboration

Last Updated: 2026-10-15

## Start here

- Read `docs/HANDOFF.md`, then inspect branch, working tree, and recent commits.
- Continue the current milestone; distinguish approved product choices from review suggestions.
- One editing agent at a time in this checkout. Use separate worktrees if simultaneous work is explicitly requested.
- Current collaboration branch: `pi/helixtune-foundation`. The user authorized local checkpoint commits for this work. Do not push or publish without authorization.
- Preserve unrelated or unfinished work. Checkpoint complete milestones and update the handoff before switching agents.

## Hardware and private inputs

- Protocol and parameter semantics are provisional until verified against Windows captures. Emulator success does not establish hardware compatibility.
- Do not automatically connect to hardware. Current foundation milestones use emulator/synthetic data only.
- No firmware writes. Keep vendor binaries, extracted parameter maps, private captures/backups, credentials, and user state out of Git.
- Never use the user's `~/.helixtune` state for tests; use temporary directories.

## Validation

- Python: `uv run pytest -q` (or `.venv/bin/python -m pytest -q`).
- Frontend, from `web/`: `npm ci`, `npm run check`, `npm test`, `npm run build` as appropriate. Dependencies already installed locally need not be reinstalled.
- Built UI goes to ignored `src/helixtune/web/dist/`; rebuild after frontend changes.
- Run focused regressions, then relevant suites once. Record counts and skipped private-input tests in the handoff.
- New foundation tests should run without proprietary artifacts or personal backups.
- API tests must exercise real owner/agent authentication. Use the test-only `owner_client` helper for owner fixtures; do not add a production authentication bypass. See `docs/ACCESS.md` for bootstrap and scopes.

## Handoff

Update `docs/HANDOFF.md` with completed checkpoints, validation, unresolved limits, and the next concrete task. Keep AIKB as a short index pointing here. Do not send cross-agent messages unless the user requests them.
