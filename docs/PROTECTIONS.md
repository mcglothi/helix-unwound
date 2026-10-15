# Physical-output constraint review

Last Updated: 2026-10-15

## Design and authority

A numerical limit being enforced is separate from its source being verified. Every
constraint starts **pending**. Pending and **owner confirmed** constraints enforce
equally, independently of tune snapshots, mute, role labels and source deletion.
A source string such as `manufacturer+confirmed` is editable metadata and grants
no authority. Confirmation is a separate owner-only operation with evidence.

`protections.json` version 2 stores individual constraints and their review history.
The effective output limits are the strictest combination of all pending and
confirmed records. Each record binds its exact numerical limit and units, output,
source specification value/unit/reference, and driver identity/assignment. Role
rules bind the relevant policy and current driver identities; Fs-derived limits
also bind the multiplier and role context. Presentation names, notes and canvas
positions do not affect confirmation. Driver ID/make/model/serial and output
assignment do. These identities still depend on the owner's physical check.

Changing or removing a source invalidates its confirmation: the original value
remains pending and enforced, while any new source revision starts pending.
Restoring an old source does not restore old confirmation. Previously cleared
sources become pending again if reintroduced. Old review entries remain intact.

The existing numerical policy remains provisional: source unit strings are bound
for review but do not perform unit conversion. Known frequency fields are evaluated
as Hz, slopes as dB/oct. Correct metadata to those units before confirming. Role
heuristics and Fs multipliers are not verified manufacturer requirements or proof
of speaker protection. Non-numeric, non-finite, non-positive and out-of-range
protection-driving specifications are rejected before saving a design.

## Owner workflow

In the selected output's Inspector, expand **Output limits**. Review the effective
limits, individual pending/confirmed records, exact source, and prior actions.
Supply evidence/reason and confirm each source after checking its driver/output
assignment. Confirmation does not relax any limit or send a device command.

To discard an incorrect or obsolete constraint, first correct/remove its source
(role or specification). This marks the previous record as retained with a changed
or removed source. Disconnect the DSP, supply a reason, and clear that individual
record. Other constraints continue enforcing. A new valid source may still impose
the same limit. Software disconnect does **not** silence a running DSP; this is an
offline editing interlock, not a verified device maintenance/mute mode.

There is deliberately no bulk reset. The old `PUT /api/protections/{cid}` refuses
replacement and directs callers to individual review. Direct engine callers must
also use the review operation. New manual limits can be recorded through equipment
specifications; metadata alone cannot confirm them.

## Persistence and API

- Version 1 aggregate limits migrate conservatively to pending legacy records;
  their original sources are unknown. Current metadata adds separate pending
  records. Migration preserves the tune file and never infers owner confirmation.
- Protection storage uses temporary-file replacement. Corrupt/unsupported data
  fails startup rather than silently resetting limits. This is not a full database
  transaction or hardware rollback guarantee.
- `GET /api/protections` returns `version`, effective `outputs`, and `constraints`.
  Each constraint includes `state`, `current`, exact `source`, `history`, and a
  `fingerprint` binding its current review state.
- Owner-only `POST /api/protections/constraints/{id}/review` requires `action`
  (`confirm` or `clear`), nonblank `reason`, and `expected_fingerprint` from GET.
  Stale submissions are refused. Only current pending sources may be confirmed;
  only noncurrent enforced records may be cleared, with no device attached.
- Agent credentials can read review state and propose/edit tuning metadata, but
  cannot confirm or clear constraints. All tune adoption paths retain protection
  checks. No HTTP payload source label changes these privileges.

Review with temporary state until Tim explicitly authorizes migration of the
existing development server's real data directory. Protocol/hardware validation
and rendered desktop/phone acceptance remain separate work.
