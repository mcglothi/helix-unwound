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

Physical transports currently accept only the exact identify request. Other
transactions fail before resetting buffers or sending bytes, even when a caller
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
the exact current RAM tune. No new stored-memory reader or selection/store command
is enabled in the application by this checkpoint.

The capture notes also show linked PC-Tool edits. The engine does not yet model
those link groups. Gain quantization, Director interaction, Save&Store/flash writes
and the unsupported operation families remain explicit follow-up work.
