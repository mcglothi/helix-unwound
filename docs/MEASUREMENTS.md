# Reviewing measurement hardware

Last Updated: 2026-10-15

The Measurements view lists stored captures with their date, seat, output tags,
capture-time tune, hardware status, and review history. It does not acquire new
measurements or prove microphone calibration, acoustic phase, or protocol behavior.

## Historical and installed drivers

Hardware at capture and hardware installed now are separate records. Unknown
captures start with blank capture-driver fields. Importing an old file never
copies today's equipment into its history. A GB60 measurement remains historical
after replacing the installed driver with a GS690; recording that historical
hardware does not make the capture eligible for tuning the replacement.

Use capture notes, installation records, or other evidence to enter the drivers
that actually played during capture. **Review installed drivers as capture
hardware** is an explicit shortcut only when that evidence establishes that those
exact drivers were installed then. It requires a separate review checkbox and
written evidence before saving. It is not a way to repair stale measurements.

Historical driver rows have independent identities. If a capture really used a
currently installed component, explicitly reviewing its installed identity links
the record to that component. Model names alone are insufficient to establish
that two physical installations are the same.

An owner can correct a mistaken existing record, but must explicitly confirm the
correction and give a reason. The previous identities are retained. An owner
statement is auditable evidence, not an independently verified fact; the software
cannot establish which drivers physically played in a historical capture.

## Capture details

Tag all outputs that played, choose the seat, and attach the scene that was
actually active during capture if known. Do not choose today's tune just to
enable assisted tuning. Unknown baselines remain unknown.

Changing output tags, seat, or capture-time tune invalidates hardware confirmation
and retains the prior record in history for review. Renaming a capture or editing
listening notes does not invalidate it. Saving capture details never changes the
current DSP tune or installed equipment.

Hardware status alone does not establish optimisation eligibility. The recorded
identities must match the installed drivers and a capture-time tune must exist.
Measurements without a known tune cannot act as predicted level anchors, even
after their hardware has been recorded. The existing selection rules still choose
which eligible measurements an assisted operation consumes.

## API

- `GET /api/measurements` lists enriched metadata, without raw frequency/SPL arrays.
- `GET /api/measurements/{id}` includes hardware status, eligibility, current driver
  identities, capture fingerprint, and record history.
- `PATCH /api/measurements/{id}` updates metadata; `tune_snapshot` attaches a scene,
  and `clear_tune: true` marks the baseline unknown. They are mutually exclusive.
- Owner-only `POST /api/measurements/{id}/attest` now **requires a body**:

```json
{
  "drivers": {
    "A": [{"id": "historical:2018-left-door", "make": "Audiofrog", "model": "GB60"}]
  },
  "reason": "Capture notes identify the drivers installed on this date",
  "expected_fingerprint": "<capture_fingerprint from the metadata response>",
  "correct_existing": false
}
```

Every measured output must have a nonempty list of distinct driver identities.
The fingerprint prevents submitting a review of changed capture data. Replacing
an existing hardware record requires `correct_existing: true`. A stale review or
unconfirmed correction returns 409 `measurement_conflict` without changing the
record. Agent credentials cannot attest. There is no HTTP shorthand that silently
uses the current installation. Trusted in-process calls retain a compatibility
helper; HTTP clients must always provide explicit identities and evidence.

Hardware attestations/corrections and invalidations append history in the stored
measurement; saving uses atomic replacement so readers cannot see partially written
JSON. Existing measurements without history remain readable. This is not a complete
crash-durable event store, and backups remain important.

## Remaining limits

The Studio system display still combines stored seat measurements without the
solver's provenance filtering; prediction-display honesty is a separate checkpoint.
Magnitude-only measurements cannot establish crossover phase or summation. Acoustic
verification and Windows protocol captures remain necessary before live writes.
Rendered browser/phone acceptance of this view is still outstanding.
