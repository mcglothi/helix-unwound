# Access and physical output protection

Last Updated: 2026-10-16

## Migration and normal startup

Start `helixtune serve`, then run `helixtune open` in a second terminal. Both commands
accept `--data` and `--port`; use the same values. The open command always targets
loopback and does not print credentials. Build the Svelte frontend first on a fresh
checkout. The legacy page can use the owner cookie after signing in through the
primary UI; it does not implement its own sign-in form.

On first startup the engine creates `auth/owner.token` and `auth/agent.token` under
the chosen data directory. The directory is mode 0700; token files are mode 0600.
Existing credentials are reused across restarts. They are not stored in tunes,
snapshots, events, or browser localStorage. Do not commit or share them.

`helixtune open` puts the owner credential in a URL fragment. Browser code removes
the fragment before API calls, then exchanges it via POST for an HttpOnly,
SameSite=Strict session cookie. API state and mutations require authentication.
Cookie-authenticated mutations also require an Origin matching the request's
origin (including port). No cross-origin API access is enabled. HTML and static
assets are public but contain no live state.

For phone access, open the engine URL and enter its owner credential. Automated
short-lived pairing, per-device sessions, and a native Mac launcher are future work.
The server uses HTTP; credentials and cookies are not encrypted in transit. Keep
remote access on a trusted network or use an encrypted tunnel. No cloud is required.

Use **Sign out** in the header to clear that browser's owner session.

## Capabilities

| Principal | Capability |
|---|---|
| Unauthenticated | Static UI and owner-session credential exchange only |
| Agent bearer token | Read state; mutating routes **explicitly opted in** with `@agent_allowed`: tune/channel edits, proposals (create, apply, discard), A/B, scene save/load and preset/measurement import (no overwriting existing names), targets, equipment/wiring add + edit, layout, media upload/caption, themes |
| Owner bearer token / owner browser session | Everything, including all deletions, device connect/disconnect, full overwrite, physical-output reconfiguration, measurement provenance attestation, and replacing an existing scene (`overwrite: true`) |

Capabilities are declared per route. An app-wide dependency runs after routing and
refuses agent credentials on any mutating route whose endpoint is not marked
`@agent_allowed`, so **new or unclassified routes default to owner-only**. Read
methods (GET/HEAD/OPTIONS) are available to both principals. A regression adds an
undecorated route at test time and proves the agent receives 403.

Saving a scene or importing a preset under an existing name returns 409 `exists` for
every principal; only the owner may retry with `overwrite: true`. Deletion is
owner-only and permanent today; trash/recovery is planned separately.

The agent credential is a bounded tuning-editor credential, not proposal-only.
`x-helixtune-source` is an owner-controlled audit label. It neither grants nor
removes capabilities; agent events are always attributed to the authenticated
agent principal. Owner checks live in the HTTP boundary, independent of MCP's
advertised tool list.

MCP reads the agent token from `HELIXTUNE_DATA_DIR` (default `~/.helixtune`). Set
`HELIXTUNE_URL` for a different engine address. An explicit `HELIXTUNE_TOKEN`
overrides file lookup; use an agent credential, not an owner credential.

This is not an OS sandbox: code running as the same user with access to owner
credential files can assume owner authority. Direct Python engine calls and CLI
hardware commands are trusted local operations. Do not claim protection from an
adversarial process with the owner's filesystem access.

To rotate a credential, stop the engine, remove the relevant token file, and
restart. Existing browser sessions must sign in again after owner rotation. There
is no credential-management endpoint or per-agent attribution/revocation yet.

## Persistent physical output limits

The engine creates version 1 `protections.json`, keyed by physical outputs A–J.
On upgrade it derives conservative limits from the current tune and equipment;
it does not rewrite the tune or infer physical wiring from old snapshots.
Malformed or unknown-version protection files stop startup instead of being reset.

Each output records a minimum high-pass frequency and slope, optional maximum
low-pass frequency, and an Fs multiplier. Accepted tune roles and recorded driver
specifications can only tighten this record. Removing specifications, reassigning
equipment, changing role labels, muting/unmuting, snapshots, undo, A/B, proposals,
whole-tune replacement, and full pushes cannot bypass it. Gain and EQ ceilings
also apply to outputs labeled unused. Muted outputs may stage missing crossovers,
but unmuting rechecks physical limits.

Protection records are saved before device writes. If a write fails, a stricter
record can remain even though the prior tune is retained; it is never silently
rolled back to weaker limits. Writes remain uncertain under the existing recovery
rules. Limits do not establish safe power, excursion, aggregate filter headroom,
or actual hardware filter behavior.

To change a physical driver:

1. Disconnect the device in the workstation (read-only connections count too).
2. Correct stale role labels and equipment specifications; mute the output for
   offline setup if its staged filters do not satisfy the retained limits.
3. Open Studio's output protection panel, enter the intended limits, and confirm
   reconfiguration. This owner-only operation replaces that output's saved record.
4. Current roles/specifications are reapplied as minimum constraints. Review
   `/api/safety/check` and tune settings before any reconnect/full overwrite.

The API equivalent is `PUT /api/protections/{cid}` with an owner credential and
body `{"protection": {...}, "confirm": "RECONFIGURE"}`. The protection object is a
replacement: omitted fields take their defaults. No device write occurs when
reconfiguring these settings.

## Validation

Tests use temporary directories and synthetic addresses. Access regressions cover
anonymous requests, real owner/agent credentials, source-header spoofing, cookies,
cross-origin mutations, bootstrap handling, and MCP credential selection. Protection
regressions cover migration, persistence, all adoption paths, role/spec removal,
muting, explicit reconfiguration, and invalid equipment data. Hardware verification
and rendered browser/phone acceptance are separate outstanding checks.
