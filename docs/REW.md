# Read-only REW capture browser

Last Updated: 2026-10-18

In Measurements, expand **Bring measurements from REW**. On the engine computer,
start REW's API (launch REW with `-api`, e.g. `open -a /Applications/REW/REW.app --args -api`,
or enable it in Preferences). **The API needs a REW 5.40 beta "-api" build**; stable 5.31.3
reports "API not supported in this build". Beta builds are downloaded from AV Nirvana
(forum login required). Browse captures, select one to preview, identify
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
Fixture-backed tests cover formats, refusals and provenance; unsupported schemas fail
explicitly rather than guessing.

**Live acceptance (2026-10-18, macOS, REW 5.40 beta 135, API 0.9.8, loopback only):**
discovery accepted the live `/doc.json` (Swagger 2.0, 378 paths) and measurement list. A
synthetic response (20 Hz-20 kHz, 48 points/octave, +6 dB bump at 100 Hz) was imported into
REW through its own `/import/frequency-response-data` endpoint, then read back by
`RewClient.capture`: 479 points, maximum error 0.0000 dB. Through the HelixTune API,
discover -> preview -> import created a library measurement, and a repeated import returned
the existing record. The synthetic curve was then deleted from REW. A real microphone
measurement has not yet been imported. Note: right after launch REW briefly answers
`/doc.json` with 404 while the API starts; retry after a moment.
