# Saved sessions and recovery

Last Updated: 2026-10-15

The workstation saves its accepted tune, up to 200 Undo and 200 Redo entries,
and both A/B slots in `workstation.json` (version 1). Saving uses a temporary file,
flush/fsync, atomic replacement and directory fsync on POSIX. The previous
validated checkpoint is kept in `workstation.previous.json`. A failed device
operation does not advance either the accepted application tune or its checkpoint.

Only one running engine should own a data directory. This format is an application
checkpoint, not a backup of everything: equipment, measurements, output protections,
scenes, targets and credentials remain separate. Events and proposals are not
restored as part of the checkpoint. Restoring a tune cannot relax independently
stored physical output constraints. Undo and Redo recheck current protection rules.

## Restart and migration

Restart restores the workstation without opening a port, enabling writes or
claiming that the DSP contains the saved tune. Connect deliberately and review a
full overwrite before incremental writes can resume. A/B selection describes the
workstation comparison; it is not hardware readback evidence.

If no workstation checkpoints exist, the legacy `current.json` is loaded. The first
accepted change, A/B assignment or explicit retry-save creates the new checkpoint.
No automatic startup migration rewrites a legacy tune. Once a checkpoint exists,
`current.json` becomes an atomic compatibility export, not an input: editing it
will not override the checkpoint. Older applications do not understand durable
history; preserve the whole state directory before switching versions.

## Unreadable or unsaved state

An unreadable/missing primary checkpoint falls back to the previous validated
checkpoint with a visible notice. This can lose the most recent accepted changes;
review the recovered tune. The recovery copy is not replaced with a malformed
primary on the next save. If neither checkpoint can be read, startup stops instead
of silently substituting defaults or a stale export. Unsupported versions also
stop instead of silently downgrading. Preserve damaged files for diagnosis and
restore a known-good backup; do not delete them to force a fresh session.

If saving fails after a device has accepted writes, the engine retains the new
accepted tune in memory and displays a persistent warning with **Retry saving**.
It does not report that the edit was rejected or pretend the DSP rolled back.
Keep the app running, fix storage access/capacity and retry. A separate message
identifies a compatibility-export failure when the canonical session was saved.
These guarantees do not establish resilience against all filesystem/hardware
failures or semantically valid data corruption; there is one previous checkpoint,
not a replacement for independent backups.

## Validation

Synthetic regressions cover restart with Undo/Redo and A/B slots, final history
on scene/A-B changes, redo invalidation, bounded history, protection rechecks,
legacy adoption, malformed/missing/future checkpoints, failed atomic replacement,
disk-full retries and failed device writes. No real user data is migrated in tests.
