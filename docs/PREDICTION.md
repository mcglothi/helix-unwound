# Acoustic estimates and their evidence

Last Updated: 2026-10-15

The main response graph is a **magnitude estimate**, not a measurement of the
current complete system. It combines the selected capture magnitudes with changes
in modeled EQ/crossovers/channel gain/mute and the difference between current and
capture-time master gain. Master gain is applied once, outside the individual
channel transfer functions and their numerical clipping floors.

## Selection

Studio, Drive, proposal previews and the solver level anchor use a common selection
rule at the requested seat:

1. Require recorded capture hardware matching current driver identities and a known
   capture-time tune. No attestation is inferred from a file name, date or import.
2. Refuse missing/duplicated/unknown output tags, invalid frequency/level arrays,
   captured muted outputs, or changed input routing. Changed delay/polarity in a
   combined capture is also refused because individual acoustic phase is unknown.
3. Prefer isolated captures over combined ones, then newer captures; break exact
   timestamp ties by measurement ID. Include a capture only if none of its outputs
   overlap an already selected capture. This may leave some outputs uncovered;
   coverage is reported instead of double-counting or inventing a response.

The graph's source details identify contributors, captured bandwidths, excluded
captures with reasons, and uncovered active/unmuted role-assigned outputs. Hardware
matches still depend on owner-provided records; a matching identity is not
independent verification of a physical installation. Display and solver selection
cannot rescue inaccurate capture metadata.

`GET /api/system` adds `available_measurement_count`, `contributors`, `excluded`,
`coverage`, `aggregation`, `phase_verified` (false) and `limitations`.
`measurement_count` means selected contributors. No eligible captures means null
measured/predicted/target curves rather than an invented reference. Historical raw
curves remain available through the library/API; their per-capture `predicted`
curve is null when projection is ineligible, with `prediction_issues` explaining why.
Combined captures are never copied into individual output curves. A mixed-role
combined capture appears under `mixed`, rather than being attributed to its first
output's role. The target's display level follows the selected estimate's 300 Hz–
3 kHz mean, so its height is not an independent absolute SPL reference.

## Limits

Separate captures are combined using an incoherent **power sum**. This does not
establish coherent acoustic addition/cancellation, crossover alignment, delay,
polarity, or phase response, even if a stored capture has phase data. No phase/time
reference compatibility has been established. For a combined capture, relative
filter changes are approximated by the change in the channels' electrical power
sum; the capture cannot identify each driver's contribution.

Deep attenuation and mute are represented by numerical floors, not a verified
noise floor or silence. Frequencies outside a capture's bandwidth use edge-value
extension; inspect its bandwidth before relying on those portions. Captures must
have comparable playback/recording levels. Absolute SPL calibration, clipping,
aggregate headroom, power/excursion and hardware filter behavior remain unverified.
The final tune always needs a fresh acoustic measurement.
