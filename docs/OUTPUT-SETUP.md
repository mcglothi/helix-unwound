# Output setup and keyboard navigation

Last Updated: 2026-10-15

Setup → System now shows physical outputs A–J in socket order, alongside input
routing, role, mute setting, recorded speakers, electrical filters, output limits
and pending protection reviews. Recorded speaker assignments come from System;
the map does not infer actual wiring or capture-time measurement identities.
An unused role is a label, not a mute command, and an unused output that still
routes audio is called out explicitly.

**Edit name, role & route** opens a local draft. Custom input weights are preserved
unless a replacement route is deliberately selected. **Review changes** shows the
before/after values. The final action distinguishes a workstation save from an
update that will be sent to a synchronized, write-enabled DSP. No connect, full
push, measurement or excitation occurs on opening this view. Crossover, gain,
delay and mute are edited separately in Studio.

The review is bound to that output's full settings, equipment design, protection
rules and device connection/send state, including the current server instance.
If those change, saving returns 409 and the draft stays visible; reopen to review
current settings. An edit to another output remains mergeable. The owner-only
PUT endpoint checks under the engine lock and uses the same validation,
protection, Undo and device-failure paths as other tune edits. An interrupted
write does not adopt the draft, and marks device state uncertain. Disk-save
failures follow the session-recovery rules in `SESSION-RECOVERY.md`.

## Explicit Off versus legacy routing

The earlier model treated ten empty input mixes as a legacy tune and restored
alternating L/R routes during validation. Explicitly selecting Off on the last
routed output could therefore re-enable all routes. This is fixed: only serialized
tunes whose channel records all **omit** the `mix` field receive legacy defaults,
assigned by physical ID rather than row order. Explicit empty mixes remain Off
through validation, persistence, restart and Undo/Redo. Model objects with explicit
empty mixes also stay Off. No hardware is accessed by this migration.

## Keyboard and small screens

- Cmd/Ctrl+Z: Undo; Cmd/Ctrl+Shift+Z: Redo; Ctrl+Y also supports Redo.
- `[` / `]`: previous/next physical output in Studio, wrapping A–J.
- `?` or **Keys**: shortcut help. Escape closes dialogs.
- Tune shortcuts pause inside input/select/textarea/contenteditable elements,
  during composition or repeats, and while any dialog is open. Native text Undo
  remains available. Only available workstation history actions consume shortcuts.
- **Skip to workstation** is available on keyboard focus. Studio's output selector
  appears above the graph, and **Jump to controls** moves focus to the inspector.
- The narrow-screen header scrolls away instead of covering the tuning controls.
  Output cards collapse into one column; dialogs are bounded and scrollable.

Rendered acceptance used an isolated synthetic demo on port 8782 in native Brave:
output-name edit/review/save, Cmd+Z / Cmd+Shift+Z, and a responsive 390-pixel viewport
for the control jump link and output editor/review focus/cancel. This is viewport
emulation, not physical phone, screen-reader, touch or foldable certification.
