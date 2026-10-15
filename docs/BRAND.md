# Helix Unwound — brand direction

Last Updated: 2026-10-15

Product name chosen by Tim: **Helix Unwound**.
Repository: <https://github.com/mcglothi/helix-unwound>.

## Core image

Tim's concept: a **double helix unwinds at the top and evaporates into music
notes**. The feeling is **freedom**: capable hardware gaining a new life beyond
its discontinued software support. Keep the transformation from structure to
music readable, rather than treating the notes as unrelated decoration.

The project is a community-built, Mac-first audio tuning workstation for the
HELIX DSP PRO MK2, with a headless engine, desktop/phone browser UI, and shared
human/AI workflows. The goal is a serious tool with a more playful identity.

## Directions to explore

These are prompts for design exploration, not settled visual decisions:

- A restrained, crisp helix base that opens into a freer musical shape above.
- A strong static symbol first, readable as an app icon, favicon, monochrome mark,
  and small wordmark; the full illustrative version can be richer.
- An optional short animation: strands separate, unwind upward, and resolve into
  notes. A reduced-motion/static version should carry the same identity.
- A wordmark that fits the existing Studio Console direction without looking
  like a vendor control panel. Explore light and dark surfaces and accessibility.
- Musical freedom and repair/community longevity as the story; avoid suggesting
  that the software or an AI can independently certify a safe tune.

The Python package, executable and existing API paths remain `helixtune` during
this development stretch. Renaming internals is a separate implementation task;
branding proposals can use Helix Unwound immediately.

## Useful context for external collaborators

Start with [README](../README.md), [HANDOFF](HANDOFF.md), and [DESIGN](DESIGN.md).
The design document includes aspirations; the handoff identifies what has actually
been implemented and what is still unverified. `web/src/lib/components/`,
`web/src/lib/theme.css`, and `web/src/lib/themes.ts` describe the current UI.

The GitHub repository is public for design/review collaboration. This is an early
project, not a hardware-verified release. Vendor binaries, parameter maps,
private captures, user settings and credentials are excluded. The repository is
not an official Audiotec Fischer product; brand exploration should preserve that
independent community identity.
