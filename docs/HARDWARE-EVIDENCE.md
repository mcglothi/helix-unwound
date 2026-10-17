# First USB capture reconciliation

Last Updated: 2026-10-17

Claude captured PC-Tool 4.80b communicating with a DSP PRO MK2. Codex audited the
local files offline. Raw pcaps, saved user presets and vendor parameter maps stay
outside Git. No Helix Unwound hardware connection or write was made for this work.

## Corrected assumptions

| Item | Capture evidence and implemented behavior |
|---|---|
| Parameter write | `03 00 01 addr16BE` followed by whole 32-bit words; length comes from the frame. Former `05 addr len data` encoding was wrong. |
| Parameter acknowledgement | Exactly `03 00 01 addr16BE`, on the expected frame channel. Wrong command/bank/address/length/channel now fails the write and invokes existing uncertainty handling. |
| Former RAM read | Removed the guessed `04` RAM read. `04/05` belong to preset storage. Both opcodes remain blocked, including on write-enabled clients; there is no generic RAM readback implementation. |
| Identify | Captured payload is 174 bytes; total framed length is 179. Emulator corrected accordingly; its payload contents remain invented. |
| Framing / sync | TX length N+1, RX N, sum8; the documented baud-switch sync burst is ten `42 00` pairs. |
| Crossover placement | HP uses biquads 0–2 and first-order section 1; LP uses biquads 3–5 and first-order section 2; stage6 stays identity in observed cases. Missing filters preserve their bank instead of shifting the other filter. |
| Q | Captured LR24 two-pole Butterworth kernel uses 0.707. The mapping profile uses that value; generic analytical filter design keeps its exact default. Other kernel orders are not rounded speculatively. |

Offline command audit: **30 capture files**, **93 parameter-write payloads**
reconstructed exactly by the corrected builder, and **93 matching acknowledgement
payloads**. This checks the observed structures, not exhaustive timing/retry cases.
The three controlled HP70 LR24, HP70 LR12 and LP400 LR24 cases each matched the
corrected rendered words within **1 LSB**, over 18 written crossover words per case.
Remaining quantization differences are not represented as byte-exact equivalence.

## Hardware write quarantine

Physical transports accept exact identify and bounded `32 03` stored-preset
reads only (see `STORED-PRESET-BACKUP.md`; 19200/session-free access awaits the live test).
Other transactions fail before resetting buffers or sending bytes, even when a caller
sets `allow_writes=True`. Engine attachment also refuses non-emulator write-enabled
clients, and the owner API rejects physical write-enabled connection requests
before opening a port or replacing the existing connection. The UI keeps physical
write permission disabled; offline editing and emulator workflows remain available.
No override switch was added. Older already-running processes retain their old
implementation until restarted and must not be used for writes.

This is intentional until session lifecycle/baud handling, master gain, routing,
first-order writes, other slopes and parameter semantics receive independent
coverage. Slopes that need more than the captured three-biquad bank per filter
are refused instead of borrowing another bank; higher-slope layout needs evidence.
A valid write echo is an acknowledgement, not independent acoustic or RAM readback.

## Stored preset is not current RAM

The capture tools discovered `32 03 PP OO NN` stored-memory reads: the stored
preset includes a name and qCompress XML data. That is promising for a future
**stored-preset backup/import** workflow. It cannot yet be called a live RAM backup:
unsaved RAM edits may differ. The stored preset found in the captures is newer
than the old local backups, so neither those backups nor its timestamp establish
the exact current RAM tune. A bounded stored-memory reader is now available as a separate explicit backup
action; no session, baud-switch, selection or store command is enabled by it.

## Quantization and link groups (2026-10-17, Claude Code)

- **8.24 quantization truncates toward zero.** Importing the stored 2022 preset, applying
  the same UI edits PC-Tool made and rendering reproduces all 143 parameter words of
  captures 04-12 bit-exactly with truncation; `round()` matched 109, floor 115, ceil 89.
  `dsp/fixed.to_824` now truncates (regression: `test_824_truncates_toward_zero_like_pc_tool`).
- **Link groups.** `.afpx` `LG` is PC-Tool's link group (0 = unlinked). In the captures an
  edit on A was written to A and B (LG=2) for EQ bands (the whole edited band), crossovers,
  gain, mute and polarity; delay was written to A only. Linked channels can still hold
  different values (A and B have different EQ in the stored preset): PC-Tool copies the
  edited item, it does not force the channels equal. `Channel.link_group` is imported, the
  channel/band/crossover/EQ-reset endpoints and MCP tools copy the edited item to linked
  channels (`?link=false` / `link=False` edits one channel), and the UI shows and can unlink
  a channel. Whole-tune replacement and proposals set every channel explicitly and are not
  propagated.

## Protection tiers (2026-10-17)

High-pass protection is reported in three tiers. **Red (blocks):** role floors and
manufacturer-published limits; also the Fs-multiple margin for a driver whose manufacturer
publishes no minimum (it is then the only driver-specific floor). **Yellow (allowed,
reported):** the Fs-multiple margin of a driver whose manufacturer minimum is lower, e.g.
Audiofrog GB25: manufacturer 200 Hz / 12 dB/oct is enforced, 1.5 x Fs = 255 Hz is advisory,
so Tim's long-running 220.67 Hz mid high-pass is yellow and 190 Hz is red. **Green:** above
both. Recorded constraints keep their provenance; `ProtectionBook.is_advisory` classifies the
Fs constraint as advisory only while the same driver's `hp_min` constraint is not cleared.
`/api/status` and `/api/safety/check` return `advisories`; the UI shows them in the
`--caution` (base16 yellow) colour.

## Session layer (2026-10-17, emulator-first)

`protocol/session.py` replays PC-Tool's captured sequence. Open: baud recovery at 19200
(`0A 03`, sync, host high; `0A 2F`, sync, host low - returns a DSP left at high speed),
identify (PRO MK2 only), `09 01`, `0A 03`, sync, ~0.5 s, host 230400, sync, keep-alive
check. Idle: keep-alive `02 00 22 b8 00 00 00 00` echoed (engine pinger every 0.8 s under
`serve`; a missed echo marks the device `uncertain`). Close (also on detach): `09 00`,
`0A 2F`, sync, ~0.5 s, host 19200. Baud acks are truncated on the wire and are drained, not
validated. The engine opens a session only for write-enabled attaches; read-only attaches
send identify only. The emulator models its line rate (frames at the wrong host rate are
noise) and the captured truncated acks. Physical transports still reject every session byte
(`Client` gate) - enabling them is a separate, supervised step after the live read test.

Director interaction, Save&Store/flash writes, master volume, routing and the
unsupported operation families remain explicit follow-up work.
