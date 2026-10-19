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

**Captured just now (one step).** While a DSP (or the emulator) is connected and
synchronized, the capture-time tune list offers *On the DSP now (just captured)*, selected by
default. With the outputs tagged and the owner's explicit confirmation ("these outputs were
playing the tune on the DSP, through the drivers currently recorded in Setup"), import stores an
exact copy of the workstation tune as the capture-time tune and attests the currently recorded
drivers in the same operation, so the capture can feed estimates and assisted tuning
immediately. It is bound to the workstation revision and connection epoch seen when the
preview opened (any change refuses), requires recorded drivers on every tagged output, and
records `capture_context` (epoch, revision, applied-image and design fingerprints, limits) in
the import provenance. This is an owner statement, not hardware verification: synchronized means
acknowledged managed writes only; master gain is excluded on hardware; the Director or head unit
can change state outside the workstation; nothing is read back. Seat names are normalised
(trimmed, lower case) for every measurement and when selecting by seat.

HTTP entry points: owner-only `GET /api/rew`,
`GET /api/rew/measurements/{uuid}` (optional `port`), and
`POST /api/rew/import` with `uuid`, `port`, `expected_fingerprint`, optional
`channels`, `seat` and `tune_snapshot`, or `captured_now` with `owner_confirmed`,
`expected_revision` and `expected_connection_epoch`. Requests have finite timeouts/response limits,
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

**What the API can drive without REW Pro (tested 2026-10-18, REW 5.40 beta 135, Mac muted):**
`POST /measure/command {"command": "SPL"}` returns **401 "A Pro upgrade license is required
for this action"** (nothing played), matching the API help ("automated sweep measurements
requires a Pro upgrade license"; the upgrades page does not mention it). Without Pro:
`/generator/command` Play/Stop works (signal set with `POST /generator/signal
{"signal": "pinknoise"}`), and `/rta/command` Start/Stop/"Reset averaging"/"Save current"
works; "Save current" stores the RTA trace as a REW measurement, which the existing import
reads. A one-click "Measure this seat" can therefore use pink noise + RTA averaging
(moving-mic method, common for in-car tuning) without Pro; sweep automation would need Pro.

**Measure this seat (built 2026-10-19, `helixtune.measure_run`).** Drive view -> *Measure this
seat*: choose outputs (presets: front drivers, subwoofers, everything playing), seat, averaging
time and noise source (REW's generator over the Mac's audio, e.g. Bluetooth to SYNC, or noise the
owner plays). Requires a connected, synchronized DSP, recorded drivers on each output, no
unacknowledged state fault, every chosen output unmuted, and REW's **RTA window open** (REW only
analyses input while it is "enabled"; otherwise "Save current" returns "Nothing to save"). Per
output: one validated engine edit isolates it (no link-group propagation), settle, reset RTA
averaging, average while the owner moves the mic, "Save current", find the new REW UUID, import
tagged with the output, seat, exact isolated tune and current drivers (attested in-process),
magnitude only, `capture_context.kind = measure_run`. Revision/connection changes, Stop, REW
errors and lost connections abort; cleanup stops generator/RTA and restores only the run's own
mute changes when the connection is still trustworthy. `measure_run.json` (durable) lets a
restart report an interrupted run (`status.interrupted_measure_run`, restore or discard).
Owner-only API: `POST /api/measure/runs`, `GET /api/measure/runs/current`,
`POST /api/measure/runs/current/stop`, `POST /api/measure/interrupted`. Live acceptance:
silent run (external source) against REW 5.40 beta 135 with the emulator, outputs A and C,
3 s each: both captured, current, mutes restored, captures lead the estimate. Not yet run with
the UMIK-1 in the truck or with REW's generator audible.

**Time alignment by crossover summing (built 2026-10-19).** Measure dialog -> *Time alignment*:
choose a reference output, the output whose delay is adjusted, and outputs to carry with it (so
already-aligned pairs keep their relation). The pair needs a shared crossover (one output's
low-pass meeting the other's high-pass; fc = their geometric mean). Steps (odd, default 9) span
about one period of fc around the current delay (delays never go negative). Sequence: every
output muted -> RTA noise floor; pair isolated; for each step a validated delay edit (recovery
intent saved first), swept twice (adjusted output's polarity as set, then flipped), settle, reset averaging, average with the **mic held still**, read the live
RTA average (`/rta/captured-data`, no REW measurement saved) and score the power mean over
fc/2..2fc on a log grid; then the winning setting and the starting delay are each measured again. A half-period delay only mimics a polarity flip near fc, so the broadband score separates a reversed driver from a timing error; a winning flip is proposed with the delay and flagged. Guards (from a live run that
scored cabin noise): the loudest step must be >= 10 dB above the floor, and a proposal is made
only if the twice-measured gain beats max(0.5 dB, 2 x the larger repeat difference); the shared crossover must be one low-pass meeting the other's high-pass within an octave; the proposal is bound to the capture-time processing and drivers of every involved output (Codex review of 92bb761). Delays and mutes are restored
under the same ownership/trust rules as measurement runs; the result is an `alignment`
**proposal** (delay edits with before-values) for owner review, never applied by the run.
Magnitude-based: it optimises how fully the pair sums at that seat, not timing or phase.
Owner-only `POST /api/measure/align`. Live: silent runs against REW 5.40 beta 135 with the
emulator confirmed the data path and that cabin noise is refused; not yet run with pink noise in
the truck.

