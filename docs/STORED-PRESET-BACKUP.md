# Read-only stored-preset backup — step 1

Last Updated: 2026-10-17
Status: implemented and tested offline; **Mac/DSP access at 19200 without a session
is not yet live-validated**. No automatic hardware connection is performed.

## What it does

The physical command allow-list accepts only exact identify (`08`) and bounded
stored-memory reads (`32 03 PP OO NN` with a zero-filled body, within the 64 KiB
address space). The name is one18-byte read at address0; data reads start at18 or
later, with1–128 bytes per request. Captured request body sizes are NN for the name
and NN+1 for compressed data; the implementation zeros those buffers rather than
replaying incidental PC-Tool buffer contents. Compressed-data replies carry NN
bytes plus one zero trailer, which is validated and excluded from the data.
It does not admit other `32` subcommands, including slot selection, or `09`
session commands, `0A` baud switching, RAM writes, preset stores or unknown probes.
Physical write enable remains blocked. The OS serial port is opened at 19200 8N1.

The reader compares two full reads of the exposed stored preset, validates reply
command/page/offset/length/channel, and extracts the first complete qCompress
stream starting at offset 18. The four-byte uncompressed-length header is bounded
at 4 MiB. Decompression stops at zlib EOF, ignoring trailing memory bytes; the final
request can necessarily read up to 127 bytes beyond that EOF. Compressed reads
cannot run past 64 KiB and both passes share a 60-second deadline, in addition to
per-request timeouts. Invalid/non-UTF-8 XML, DTD/entity declarations, wrong device type,
length mismatches, truncation and source changes refuse a backup.

Two matching reads detect observed changes; they do not establish an atomic
hardware snapshot. No preset is selected first. The file is the **stored XML
exposed by the device**, not a verified copy of current RAM or necessarily the
currently selected listening preset. Unsaved RAM edits may differ.

## CLI: explicit live test when Tim is ready

Do not start this test until the Mac is connected to the DSP and Tim authorizes it.
Close other DSP-control software and disconnect any workstation connection first.
Use `helixtune ports` to inspect available ports without opening them. Then choose
a fresh output file; the destination parent must already exist:

```bash
mkdir -p "$HOME/helix-backups"
uv run helixtune backup-stored --port /dev/cu.usbserial-REPLACE_ME \
  --output "$HOME/helix-backups/stored-before-mac-test.afpx"
```

No parameter map or existing workstation data directory is needed for this CLI.
It identifies the PRO MK2, reads stored memory twice, closes the transport and
publishes a complete mode-0600 file without replacing an existing destination.
It prints both backup and decompressed-XML SHA256 values. Compressed bytes can
differ from a recompressed capture export; compare **decompressed XML bytes**.

If there is no reply at 19200, the attempt stops. It will not start a session,
change baud, select a slot or retry through broader commands. The open question
is whether a session or faster baud is necessary on this device; a timeout is
information to bring back, not a reason to lift the write quarantine. Do not
launch older app versions to work around a refusal.

Acceptance for an unchanged stored preset: identify as PRO MK2, only the allowed
read payloads on the wire, backup XML byte-identical to the capture-derived stored
XML, no active workstation adoption or device changes. If the stored preset has
changed since capture, compare with a fresh independent backup instead of assuming
the old file must match.

## Workstation UI

After an explicit read-only connection, **Connection & recovery → Read & back up
stored preset** saves an immutable `.afpx` under the workstation `backups/`
directory. Download is owner-only. A separate **Copy backup to a scene** action
uses a new scene name and never replaces an existing scene, adopts the tune,
creates a device baseline or relaxes output protections. Import warnings and
safety problems remain visible. Unmodeled preset fields stay in the raw backup;
a modeled scene is not a promise of complete preset fidelity.

These actions use owner authentication; agents cannot initiate a read, download
private backups or import them through these endpoints. Protocol mismatch/timeouts
leave the connection read-only, with no automatic session/baud fallback.

## Validation

Synthetic transports cover exact request allow-listing, fragmented replies,
address/length/channel mismatch, bounded decompression and memory exhaustion,
source changes, exclusive files, API ownership, separate scene creation and CLI
behavior. Optional private-capture replay reconstructs stored memory from the
reconnect pcaps checks actual padded request sizes and reply frames, and compares the resulting XML byte for byte with the extracted
`.afpx`; it skips when private tooling/data is absent. This replay does not validate
Mac serial timing or session-free reads at 19200.

Native Brave acceptance used a temporary synthetic transport: backup → download
link → copy to scene, with the active tune and Undo depth unaffected. The temporary
server/tab were closed afterward. No hardware or real user state was accessed.
