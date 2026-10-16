"""MCP server: lets an agent read and tune the system through the running engine.

Talks to the helixtune HTTP API (default http://127.0.0.1:8765), so the agent,
the web UI and the phone all share one live state. Every request is tagged
source=agent; the engine applies the same safety policy to it as to the UI, and
the full-overwrite command is not exposed here at all.
"""

from __future__ import annotations

import json
import logging
import os

import httpx
from mcp.server.mcpserver import MCPServer
from .access import agent_token

logging.getLogger("httpx").setLevel(logging.WARNING)
BASE = os.environ.get("HELIXTUNE_URL", "http://127.0.0.1:8765")
mcp = MCPServer(
    "helixtune",
    instructions=(
        "Tune a HELIX DSP PRO MK2 car audio processor. Channels A-J each have: role, gain, "
        "mute, polarity invert, delay (ms), high-pass/low-pass crossover, and 30 parametric "
        "EQ bands. Read state with get_overview/get_channel before changing it. Changes go "
        "live on the DSP immediately when a device is connected. Safety limits are enforced "
        "server-side; if a change is rejected, explain the problems to the user rather than "
        "trying to work around them. Boosts are limited per step, so raise gain gradually. "
        "Use undo to revert. Save a snapshot before larger experiments."
    ),
)


_NO_BODY = object()


def _call(method: str, path: str, body=_NO_BODY, params=None) -> str:
    with httpx.Client(base_url=BASE, timeout=10, headers={"Authorization": f"Bearer {agent_token()}"}) as c:
        if body is _NO_BODY:
            r = c.request(method, path, params=params)
        elif body is None:
            # httpx json=None means no body, whereas a crossover bypass needs JSON null.
            r = c.request(method, path, content="null", headers={"Content-Type": "application/json"}, params=params)
        else:
            r = c.request(method, path, json=body, params=params)
    try:
        data = r.json()
    except ValueError:
        data = r.text
    if r.status_code >= 400:
        return json.dumps({"status": r.status_code, **(data if isinstance(data, dict) else {"detail": data})})
    return json.dumps(data, separators=(",", ":"))


def _summ_channel(ch: dict) -> dict:
    eq = [{"band": i + 1, **{k: b[k] for k in ("type", "freq_hz", "gain_db", "q")}}
          for i, b in enumerate(ch["eq"]) if b["enabled"]]
    return {k: ch[k] for k in ("id", "name", "role", "gain_db", "mute", "invert", "delay_ms", "hp", "lp")} | {
        "active_eq_bands": eq}


@mcp.tool()
def get_status() -> str:
    """Device connection state, tune name, undo depth and recent change log."""
    return _call("GET", "/api/status")


@mcp.tool()
def get_overview() -> str:
    """Compact view of the whole tune: every channel's settings and only its active EQ bands."""
    t = json.loads(_call("GET", "/api/tune"))
    if "channels" not in t:
        return json.dumps(t)
    return json.dumps({"name": t["name"], "master_gain_db": t["master_gain_db"],
                       "channels": [_summ_channel(ch) for ch in t["channels"]]}, separators=(",", ":"))


@mcp.tool()
def get_channel(channel: str) -> str:
    """Full settings for one channel (A-J), including all 30 EQ bands."""
    return _call("GET", f"/api/channels/{channel}")


@mcp.tool()
def set_channel(channel: str, name: str | None = None, role: str | None = None, gain_db: float | None = None,
                mute: bool | None = None, invert: bool | None = None, delay_ms: float | None = None,
                source: str | None = None) -> str:
    """Change channel basics. role: tweeter|midrange|midbass|woofer|subwoofer|fullrange|unused.
    Roles can tighten protection floors; changing a label cannot lower existing physical-output limits.
    source: L | R | mono (L+R
    summed at -6 dB each, e.g. for a mono subwoofer amp) | off."""
    mixes = {"L": {"L": 1.0}, "R": {"R": 1.0}, "mono": {"L": 0.5, "R": 0.5}, "off": {}}
    if source is not None and source not in mixes:
        return json.dumps({"error": f"source must be one of {list(mixes)}"})
    body = {k: v for k, v in dict(name=name, role=role, gain_db=gain_db, mute=mute, invert=invert,
                                  delay_ms=delay_ms, mix=mixes.get(source) if source else None).items() if v is not None}
    return _call("PATCH", f"/api/channels/{channel}", body)


@mcp.tool()
def set_crossover(channel: str, which: str, freq_hz: float | None = None, slope_db: int = 24,
                  type: str = "linkwitz_riley", remove: bool = False) -> str:
    """Set the high-pass (which='hp') or low-pass (which='lp') filter on a channel.
    type: linkwitz_riley|butterworth|bessel; slope_db 6..48 in steps of 6 (LR needs even orders).
    remove=True disables that filter."""
    body = None if remove else {"type": type, "slope_db": slope_db, "freq_hz": freq_hz}
    return _call("PUT", f"/api/channels/{channel}/{which}", body)


@mcp.tool()
def set_eq_band(channel: str, band: int, freq_hz: float | None = None, gain_db: float | None = None,
                q: float | None = None, type: str | None = None, enabled: bool | None = True) -> str:
    """Edit EQ band 1-30 on a channel. type: peak|low_shelf|high_shelf|notch|allpass."""
    body = {k: v for k, v in dict(freq_hz=freq_hz, gain_db=gain_db, q=q, type=type,
                                  enabled=enabled).items() if v is not None}
    return _call("PATCH", f"/api/channels/{channel}/eq/{band}", body)


@mcp.tool()
def reset_eq(channel: str) -> str:
    """Disable all EQ bands on a channel."""
    return _call("POST", f"/api/channels/{channel}/eq/reset")


@mcp.tool()
def set_master_gain(gain_db: float) -> str:
    """Master gain in dB (<= 0)."""
    return _call("PATCH", "/api/master", {"gain_db": gain_db})


@mcp.tool()
def predicted_response(channels: str = "", points: int = 48) -> str:
    """Predicted magnitude response (dB) per channel from EQ + crossover + gain.
    channels: comma list like 'A,B' (blank = all). This is the electrical filter
    response, not an in-car acoustic measurement."""
    return _call("GET", "/api/response", params={"channels": channels or None, "points": points})


@mcp.tool()
def undo() -> str:
    """Revert the most recent change."""
    return _call("POST", "/api/undo")


@mcp.tool()
def redo() -> str:
    """Restore the last undone tune, rechecking current output protections."""
    return _call("POST", "/api/redo")


@mcp.tool()
def list_snapshots() -> str:
    """Saved tunes."""
    return _call("GET", "/api/snapshots")


@mcp.tool()
def save_snapshot(name: str) -> str:
    """Save the current tune under a name."""
    return _call("POST", "/api/snapshots", {"name": name})


@mcp.tool()
def load_snapshot(name: str) -> str:
    """Load a saved tune (applied live if a device is connected)."""
    return _call("POST", f"/api/snapshots/{name}/load")


@mcp.tool()
def list_measurements() -> str:
    """Acoustic measurements (REW imports): id, name, which channels played, seat, and
    whether the tune active at measurement time is known (needed for prediction)."""
    return _call("GET", "/api/measurements")


@mcp.tool()
def measurement_vs_current(measurement_id: str, smoothing: float = 6, points: int = 60) -> str:
    """Measured in-car response and the response PREDICTED for the current tune
    (measured + change in filters since the measurement). smoothing = 1/N octave.
    Use this to judge EQ/crossover changes before re-measuring in the car."""
    return _call("GET", f"/api/measurements/{measurement_id}/curves",
                 params={"smoothing": smoothing, "points": points})


@mcp.tool()
def system_vs_target(seat: str = "driver", smoothing: float = 6, points: int = 48) -> str:
    """Whole-system view at a seat: measured sum, predicted sum for the current tune,
    the current target curve (level-matched 300 Hz-3 kHz), eligible isolated output curves,
    contributing/excluded captures, coverage, and magnitude-model limitations
    group and per channel. Power sums (phase-blind) for RTA data."""
    return _call("GET", "/api/system", params={"seat": seat, "smoothing": smoothing, "points": points})


@mcp.tool()
def list_targets() -> str:
    """Available target curves and which one is current."""
    return _call("GET", "/api/targets")


@mcp.tool()
def propose_auto_eq(channels: str = "", seat: str = "driver", max_bands: int = 8, max_freq: float = 8000,
                    replace: bool = True) -> str:
    """Compute (do NOT apply) PEQ bands that bring each channel's predicted in-car response
    toward the target shape. channels: 'A,C' (blank = every measured channel). Prefers cuts,
    caps boosts. Returns a proposal id with per-channel error before/after. Show the user the
    changes, optionally preview_proposal, then apply_proposal if they agree. Measurements whose
    drivers are unknown or no longer installed are refused (see notes); only the owner can
    attest a measurement's drivers."""
    body = {"channels": [c.strip() for c in channels.split(",") if c.strip()] or None, "seat": seat,
            "max_bands": max_bands, "max_freq": max_freq, "replace": replace}
    return _call("POST", "/api/propose/auto-eq", body)


@mcp.tool()
def propose_levels(seat: str = "driver") -> str:
    """Compute (do NOT apply) per-driver level changes to match the target, ≤3 dB per step."""
    return _call("POST", "/api/propose/levels", params={"seat": seat})


@mcp.tool()
def propose_alignment(distances_cm: dict[str, float]) -> str:
    """Compute (do NOT apply) delays from tape-measured distances (cm) from each speaker to
    the listener's head, e.g. {"A": 112, "B": 141, "E": 98}. Farthest driver is the reference."""
    return _call("POST", "/api/propose/alignment", {"distances_cm": distances_cm})


@mcp.tool()
def preview_proposal(proposal_id: str, seat: str = "driver", points: int = 48) -> str:
    """System response if the proposal were applied (compare with system_vs_target)."""
    return _call("GET", f"/api/proposals/{proposal_id}/preview", params={"seat": seat, "points": points})


@mcp.tool()
def apply_proposal(proposal_id: str) -> str:
    """Apply a proposal (goes live on the DSP if connected; safety-checked; undoable).
    Only do this after the user has agreed to the listed changes. A 409 "conflict" means
    the tune, target, measurements or recorded drivers changed since it was computed:
    nothing was changed; recompute a fresh proposal instead of retrying."""
    return _call("POST", f"/api/proposals/{proposal_id}/apply")


@mcp.tool()
def ab_toggle() -> str:
    """Switch between the A and B tunes (both must be set in the UI first)."""
    return _call("POST", "/api/ab/toggle")


@mcp.tool()
def get_system_design() -> str:
    """The whole audio system: vehicle, equipment (head unit, DSP, amps, speakers, enclosures,
    mic, power) with make/model/specs, and the wiring between them. Speakers list the DSP
    output channels that feed them."""
    return _call("GET", "/api/design")


@mcp.tool()
def update_equipment(component_id: str, make: str | None = None, model: str | None = None,
                     name: str | None = None, location: str | None = None, channels: list[str] | None = None,
                     spec_source: str | None = None, specs: dict | None = None, notes: str | None = None) -> str:
    """Record equipment details. specs: {"fs": {"value": 38, "unit": "Hz", "source": "<datasheet URL>"}, ...}
    Known driver keys: size impedance re fs qts qes qms vas xmax sd le bl mms sensitivity power_rms.
    When the user names a product, look up the MANUFACTURER's spec sheet with your web tools and
    record values with their source URL; never guess or invent T/S parameters. Recorded Fs feeds
    the safety policy's minimum high-pass for that channel."""
    body = {k: v for k, v in dict(make=make, model=model, name=name, location=location, channels=channels,
                                  spec_source=spec_source, specs=specs, notes=notes).items() if v is not None}
    return _call("PATCH", f"/api/equipment/{component_id}", body)


@mcp.tool()
def add_equipment(kind: str, name: str = "", make: str = "", model: str = "", location: str = "",
                  channels: list[str] | None = None) -> str:
    """Add a component. kind: source|dsp|amplifier|speaker|subwoofer|enclosure|microphone|power|computer|other."""
    return _call("POST", "/api/equipment", {"kind": kind, "name": name, "make": make, "model": model,
                                            "location": location, "channels": channels or []})


@mcp.tool()
def connect_equipment(src: str, dst: str, signal: str, src_port: str = "", dst_port: str = "",
                      cable: str = "", notes: str = "") -> str:
    """Record a wire. signal: speaker|line|high_level|optical|coax|usb|power|ground|remote|other."""
    return _call("POST", "/api/connections", {"src": src, "dst": dst, "signal": signal, "src_port": src_port,
                                              "dst_port": dst_port, "cable": cable, "notes": notes})


@mcp.tool()
def analyze_equipment(component_id: str) -> str:
    """Derived numbers from recorded specs: Fs-based high-pass guidance, sealed-box Qtc/F3,
    ported-box subsonic recommendation."""
    return _call("GET", f"/api/equipment/{component_id}/analysis")


@mcp.tool()
def check_safety(snapshot: str = "") -> str:
    """List safety problems in the current tune (or a saved snapshot), including limits that
    come from recorded driver specs (Fs, manufacturer high-pass / low-pass limits)."""
    return _call("GET", "/api/safety/check", params={"snapshot": snapshot or None})


@mcp.tool()
def get_safety_policy() -> str:
    """The limits the engine enforces (read-only for agents)."""
    return _call("GET", "/api/safety")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
