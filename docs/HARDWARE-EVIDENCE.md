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
the exact current RAM tune. The backup action (CLI `backup-stored`, API, engine) opens
PC-Tool's session and sends the stored-memory selection `32 01 06 00` before the bounded
reads - see the 2026-10-18 live results below. It never sends parameter writes, `04`/`05`
preset-storage commands, or any other `32` subcommand.

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
noise) and the captured truncated acks. Physical transports reject every session byte
(`Client` gate) except inside `Client.stored_backup_mode()`, which admits exactly the backup
session (start/end, baud switch, sync, keep-alive, `32 01 06 00`) and never `03` writes.

Director interaction, Save&Store/flash writes, master volume, routing and the
unsupported operation families remain explicit follow-up work.

## Live hardware test (2026-10-18, Claude Code; Tim supervising, audio muted)

Mac (FT232R via USB-C hub) and the Dell running PC-Tool, one at a time, on the truck's DSP.

**Stored-preset backup needs a session and a selection.**
- Identify answers at 19200 without a session (179 bytes, framing as captured).
- `32 03` got **no reply** at 19200 without a session, and none inside a session either,
  until `32 01 06 00` was sent. The DSP echoes `32 01 06 00`; the reads then answer.
- The selection **persists**: later the same day, `32 03` at 19200 without a session
  answered. The emulator models both (silent until selected, then persistent).
- Backup XML was byte-identical (30,852 bytes) to the copy extracted from the 2026-10-17
  capture, and identical again after the supervised write below. The flash was not changed.
- PC-Tool's `13 00 40` / `13 30 10` connect commands are **reads**. Both return erased
  memory (all `ff`), the same Friday and today. `06`, `04`, `17` and `32 00` connect replies
  were also identical across days.

**Session timing.** On macOS a command sent straight after the post-switch sync burst went
unanswered and the session failed to open. With ~0.1 s after each sync burst it opened every
time (`Session.POST_SYNC_S`). Opening a session (ours or PC-Tool's), closing PC-Tool, and
unplugging the USB cable each cause a ~1 s audio dropout. That is harmless and expected.

**First supervised write.** `GAINA` (0x232c) 5.00 -> 4.00 dB -> 5.00 dB inside a session:
both `03` writes echoed the first 5 bytes, keep-alives answered throughout, and the stored
XML read back unchanged. The 4.00 dB word equals PC-Tool's captured word.

**DSP state persistence.** Unsaved RAM changes survived an ignition cycle, so the DSP
keeps working memory while the truck is off. PC-Tool's connect + preset load replaces RAM
with the stored preset, which reverts unsaved changes.

**Director controls never cross USB.** Turning the Director knob and changing its menu
volumes while PC-Tool was connected produced no USB traffic. The Director talks to the DSP
directly.

### Incident: Digital Volume at minimum (unexplained)

After the morning's sessions and a power cycle, the DSP passed no audio (about 1 s of audio
on each preset/input switch, then silence). The Director's *Menu > Unused Functions > Digital
Volume* (the optical-input volume, `URC_FUNCTION_OPTOVOLUMEVALUE`, 0x22f9) was at minimum.
Raising it restored audio. Nobody listened after the 2026-10-17 session, so the window is
Friday's PC-Tool session through Sunday morning.

Reproduction attempts, each followed by reading Digital Volume and listening, were all
negative: identify; session open/keep-alive/close; both wrong-baud identify probes; the full
session trace; session + `32 01 06 00` + stored reads without `32 0f`; the gain write;
session + `32 0f`; the original no-session `backup-stored`; a session open without the sync
pause; PC-Tool connect/load/disconnect; a cold start; a long SYNC-volume mute (dismissed
from experience). No captured session (21 captures) ever wrote a Director volume parameter.
Possibly the Director was set by accident during testing. It is recorded as unexplained.

Safeguards: every truck test starts and ends with reading Digital Volume and confirming
audio. `DeviceMapping.protected` (matched by name: URC master/sub/opto/aux volume
values and selectors, and their slew modes, 12 parameters on 4.80b) is refused by the engine
before any write.

### Capture 23: slopes, routing, channel type

Output A high-pass at 60.83 Hz; each write burst compared with HelixTune's render of Tim's
stored tune with the same change:

| Setting | Result |
|---|---|
| Off, LR12, LR24, BW6, BW18 | bit-exact |
| BW12 | bit-exact with Q 0.71 (PC-Tool's constant; LR24 halves use .707), now implemented |
| Bessel 24 (passed through while changing characteristic) | right shape, ~1000 LSB off: PC-Tool's Bessel constants differ |
| LR36 | three biquads at 60.8 Hz with Q ~0.57 / 0.74 / 1.17, not BW3 squared; not derived |

PC-Tool offers 6/18 dB only with Butterworth. Linkwitz steps 0/12/24/36. The first-order
section goes to `FILTERS__PHASE_LP1_<ch>_..._1` for the high-pass, confirming the mapping's
first-order slot layout.

**Routing.** Removing Digital In L from Subwoofer 1 and adding it back wrote
`MAINMATRIX_..._VOL08{00..11}` (row = output I, inputs 0/1 = 0.5/0.5 -> 0/1.0 -> 0.5/0.5,
8.24, other inputs zeroed). **HelixTune's mapping currently writes channel mix to
`OPTO_MATRIX` (marked PROVISIONAL).** Which matrix PC-Tool's Main vs Digital Routing tab
edits, and how the two combine, must be settled by a capture before routing writes are
enabled.

**Channel type.** Assigning Output G a type (with the offered HP/LP preset) wrote its
crossover sections and `SUB_RC_GAIN_NX1_11_7` (0x231f).

Still uncaptured: master gain semantics (`GAIN1` is a provisional master), Save&Store,
Bessel/LR36 and higher slopes, and the Main vs Digital Routing matrix question.

