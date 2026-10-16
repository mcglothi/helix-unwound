# Read-only REW capture browser

Last Updated: 2026-10-15

In Measurements, expand **Bring measurements from REW**. On the engine computer,
start REW's API from Preferences. Browse captures, select one to preview, identify
its measured outputs/listening position and optionally its capture-time scene,
then copy it into the library. The default port is 4735; connection options allow
another local port. No arbitrary remote URL is accepted.

This adapter only issues GETs to REW's API description, measurement list and
frequency-response endpoint. It does not trigger sweeps, start audio capture,
change volume/routing, subscribe, change filters, or alter/delete REW measurements.
Helix Unwound's own import operation saves a separate local record. These routes
are owner-only, including discovery GETs; agent credentials cannot probe services.

The adapter handles big-endian Base64 float arrays, log or linear frequency axes,
and list/index-keyed measurement collections. Stable UUIDs identify captures;
ambiguous duplicate UUIDs are refused instead of guessing a numeric index.
Zero-frequency/DC bins are omitted because the workstation uses logarithmic
frequency interpolation. Original response fingerprint and summary remain in
`import_provenance`, including source date text and smoothing. Phase data can be
preserved without claiming a verified timing reference.

Preview is bound to exact source content and port. Import rereads and refuses a
changed capture; repeating an identical capture revision/assignment returns the
existing local record rather than overwriting or duplicating it. Imported records
start with unknown driver identity and no baseline tune unless the owner explicitly
selects a known scene. Source dates lack an explicit timezone, so they are retained
as source text; capture timestamp stays unknown. Import never relabels historical
hardware as today's installation. Use the normal Measurements review afterward.

HTTP entry points: owner-only `GET /api/rew`,
`GET /api/rew/measurements/{uuid}` (optional `port`), and
`POST /api/rew/import` with `uuid`, `port`, `expected_fingerprint`, optional
`channels`, `seat` and `tune_snapshot`. Requests have finite timeouts/response limits,
ignore proxy environment variables and do not follow redirects.

Reference: [official REW API documentation](https://www.roomeqwizard.com/help/help/html/api.html).
Fixture-backed tests cover formats, refusals and provenance. Live REW acceptance
is still pending; unsupported schemas fail explicitly rather than guessing.
