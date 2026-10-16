# Hardware-free demo

Last Updated: 2026-10-15

The demo is a working local workstation with an invented parameter map, virtual
three-way front stage/subwoofers, a baseline scene, eight generated response
curves and fictional equipment identities. No vendor files or DSP are required.
It exercises normal authentication, protection checks, proposals, scenes, undo,
equipment and measurement views.

From a source checkout:

```sh
uv sync --locked
cd web
npm ci
npm run build
cd ..
uv run helixtune demo
```

In a second terminal:

```sh
uv run helixtune open --data ~/.helixtune-demo --port 8770
```

The browser opens with a temporary bootstrap fragment, removes it and establishes
an owner session. The demo defaults to loopback port 8770 and `~/.helixtune-demo`,
separate from the hardware workstation's normal port/data. Both commands accept
`--data` and `--port`; use matching values. Do not point it at your real settings.

The demo refuses existing non-demo directories and incomplete/unsupported demo
state. It never resets an existing demo on restart: edits and deleted fixtures
stay changed. For a fresh example, use another empty directory. A hardware engine
refuses to open a demo data directory.

## Things to try

- Studio: select output C, request Auto-EQ, inspect the proposal and graph preview,
  apply it, then Undo. The synthetic midrange contains a deliberate peak.
- Expand output limits to inspect pending constraints and their exact sources.
- Open Measurements: the names/source identify generated curves, with fictional
  driver identities and baseline tune. These are not microphone captures or
  owner evidence about a physical installation.
- Explore Drive, System, themes and scenes. Hardware controls in Setup can attach
  only to the in-memory emulator. Full overwrite and incremental writes there
  exercise software behavior against invented addresses, not a real DSP.

The demo banner remains visible after sign-in. The backend refuses physical
serial connections before opening a port, and does not enumerate physical ports.
The engine also rejects non-emulator transports even if labelled `emulator`.
Authentication is unchanged: agent credentials cannot acquire owner device access.

An installed wheel includes the built Svelte UI when the UI was built before
`uv build --wheel`. A wheel built without frontend assets can still contain only
the legacy shell; the portable frontend CI job explicitly checks built UI inclusion.
No release artifact has been published yet.

## Validation boundaries

Mathematical fixtures and an emulator can test editing and recovery workflows.
They cannot validate hardware addresses, packet semantics, acknowledgements,
coefficient signs, noise, acoustic calibration or speaker protection.

Desktop Brave review verified the rendered Studio graph/demo banner and the
Auto-EQ preview → apply → undo flow using isolated temporary demo data. This is
limited acceptance: phone/tablet layouts, keyboard navigation, all views, session
expiry/sign-out, and protection review still need broader rendered checks.
