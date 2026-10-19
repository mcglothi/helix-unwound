# Stored-preset backup

Last Updated: 2026-10-18
Status: implemented, tested offline, and **live-validated on the truck's DSP 2026-10-18**
(Mac, FT232R). No automatic hardware connection is performed.

## What it does

The backup reproduces PC-Tool's own sequence, which the live test showed the DSP requires:

1. PC-Tool's session open: baud recovery at 19200, identify (must be a PRO MK2), `09 01`,
   switch to 230400 with sync bursts (0.1 s pause after each), keep-alive echo.
2. `32 01 06 00` (stored-memory selection). The DSP must echo it; otherwise nothing is read.
   Without it the DSP did not answer `32 03` at all, at 19200 or inside a session. Once
   sent, the selection persisted. The meaning of `06` is not decoded, so only this exact
   payload is ever sent.
3. Two full bounded reads of stored memory (`32 03 PP OO NN`), compared for equality.
4. Session close (`09 00`, `0A 2F`, sync, host 19200), always attempted, also after errors.

On a physical port the `Client` gate admits identify and bounded `32 03` reads at any time,
and the session commands above only inside `Client.stored_backup_mode()`. Parameter writes
(`03`), preset-storage commands (`04`/`05`) and every other `32` subcommand stay refused.
The OS serial port is opened at 19200 8N1 with a 0.05 s read timeout.

Read format: the name is one 18-byte read at address 0; data reads start at 18 or later,
1-128 bytes per request. Captured request body sizes are NN for the name and NN+1 for
compressed data; the implementation zeros those buffers rather than replaying incidental
PC-Tool buffer contents. Compressed-data replies carry NN bytes plus one zero trailer, which
is validated and excluded. The reader validates reply command/page/offset/length/channel and
extracts the first complete qCompress stream at offset 18. The uncompressed-length header is
bounded at 4 MiB; decompression stops at zlib EOF (the final request can read up to 127
bytes beyond it). Reads cannot pass 64 KiB and both passes share a 60-second deadline, plus
per-request timeouts. Invalid/non-UTF-8 XML, DTD/entity declarations, wrong device type,
length mismatches, truncation and source changes refuse a backup.

Two matching reads detect observed changes; they do not establish an atomic snapshot. The
file is the **stored XML exposed by the device**, not current RAM or necessarily the
currently selected listening preset. Unsaved RAM edits may differ.

## CLI

Only with the Mac connected to the DSP and Tim's go-ahead. Close PC-Tool and disconnect any
workstation connection first. Keep the audio low and read the Director's Digital Volume
before and after (see the 2026-10-18 incident in HARDWARE-EVIDENCE). `helixtune ports`
lists ports without opening them. Choose a fresh output file in an existing directory:

```bash
uv run helixtune backup-stored --port /dev/cu.usbserial-REPLACE_ME \
  --output "$HOME/helix-backups/stored-YYYY-MM-DD.afpx"
```

It prints the backup and decompressed-XML SHA256 values and publishes a mode-0600 file
without replacing an existing destination. Compressed bytes can differ from a recompressed
capture export; compare **decompressed XML bytes**. Opening a session causes a ~1 s audio
dropout, which is expected.

On a timeout or protocol mismatch nothing is written to the DSP and no file is published.
Session cleanup is attempted; if it could not reach the DSP, the next connection's baud
recovery (or a power cycle) returns it to 19200. The command does not retry through
broader commands.

## Workstation UI

After an explicit read-only connection, **Connection & recovery -> Read & back up stored
preset** runs the same sequence and saves an immutable `.afpx` under the workstation
`backups/` directory. Download is owner-only. A separate **Copy backup to a scene** action
uses a new scene name and never replaces an existing scene, adopts the tune, creates a device
baseline or relaxes output protections. Import warnings and safety problems remain visible.
Agents cannot initiate a read, download private backups or import them.

## Validation

Synthetic transports cover the exact command allow-list (including refusal outside backup
mode), the selection echo, fragmented replies, address/length/channel mismatch, bounded
decompression, source changes, a silent DSP (one read attempt, no retry, session closed, no
writes), exclusive files, API ownership, separate scene creation and the CLI wire order. The
emulator models the hardware: `32 03` is silent until `32 01 06 00`, then the selection
persists. Optional private-capture replay compares reconstructed stored memory with the
extracted `.afpx` byte for byte (skips without private data).

Live 2026-10-18: backup XML (30,852 bytes) byte-identical to the 2026-10-17 capture-derived
preset, and identical again after a supervised gain write.
