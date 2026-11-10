"""Hard limits that protect speakers. Checked before anything reaches the DSP.

Agents and the UI go through the same checks; there is no bypass flag in the API.
Edit the policy (saved alongside the tune) to change limits deliberately.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .model import CHANNELS, Role, Tune


class RolePolicy(BaseModel):
    min_hp_hz: float | None = None   # high-pass required at or above this frequency
    min_hp_slope_db: int = 12
    fs_factor: float | None = None   # when the driver's Fs is recorded: high-pass >= factor x Fs


DEFAULT_ROLES = {
    Role.TWEETER: RolePolicy(min_hp_hz=1500, min_hp_slope_db=12, fs_factor=2.0),
    Role.MIDRANGE: RolePolicy(min_hp_hz=150, min_hp_slope_db=12, fs_factor=1.5),
    Role.MIDBASS: RolePolicy(min_hp_hz=40, min_hp_slope_db=12, fs_factor=1.0),
    Role.WOOFER: RolePolicy(min_hp_hz=20, min_hp_slope_db=12, fs_factor=1.0),
    Role.SUBWOOFER: RolePolicy(min_hp_hz=15, min_hp_slope_db=12),  # subsonic filter
}


class SafetyPolicy(BaseModel):
    max_eq_boost_db: float = 9.0
    max_channel_gain_db: float = 6.0
    max_master_gain_db: float = 0.0
    max_boost_step_db: float = 3.0   # largest single-change increase in any boost
    max_total_boost_db: float = 12.0  # peak of one output's combined EQ + crossover + gain response
    roles: dict[Role, RolePolicy] = Field(default_factory=lambda: dict(DEFAULT_ROLES))


class OutputProtection(BaseModel):
    """Physical-output limits, stored outside tunes and their editable roles."""

    min_hp_hz: float | None = Field(None, ge=10, le=24000, allow_inf_nan=False)
    min_hp_slope_db: int = Field(12, ge=6, le=48, multiple_of=6)
    max_lp_hz: float | None = Field(None, ge=10, le=24000, allow_inf_nan=False)
    fs_factor: float = Field(0, ge=0, le=10, allow_inf_nan=False)


class OutputProtections(BaseModel):
    version: Literal[1] = 1
    outputs: dict[str, OutputProtection] = Field(default_factory=lambda: {c: OutputProtection() for c in CHANNELS})

    @field_validator("outputs")
    @classmethod
    def _outputs(cls, value):
        if set(value) != set(CHANNELS):
            raise ValueError(f"protection settings require every physical output {CHANNELS}")
        return value


def tighten_outputs(tune: Tune, policy: SafetyPolicy, existing: OutputProtections | None = None,
                    driver_limits: dict | None = None, *, advisory: bool = False) -> OutputProtections:
    """Learn stricter floors without ever relaxing previously recorded limits.

    The Fs-multiple margin is enforced for every driver without a manufacturer minimum
    high-pass (DriverLimits.fs_unbounded); for a driver that publishes one, that figure is the
    enforced (red) floor and its Fs margin is advisory (yellow), included when advisory=True."""
    result = (existing or OutputProtections()).model_copy(deep=True)
    for ch in tune.channels:
        guard = result.outputs[ch.id]
        rp = policy.roles.get(ch.role)
        need = rp.min_hp_hz if rp else None
        factor = max(guard.fs_factor, (rp.fs_factor or 0) if rp else 0)
        lim = (driver_limits or {}).get(ch.id)
        if lim:
            fs_basis = lim.fs if advisory else lim.fs_unbounded
            fs_margin = factor * fs_basis if fs_basis and factor else None
            candidates = [v for v in (need, lim.hp_min, fs_margin) if v]
            need = max(candidates) if candidates else None
            if lim.lp_max:
                guard.max_lp_hz = min(guard.max_lp_hz, lim.lp_max) if guard.max_lp_hz else lim.lp_max
            if need and lim.hp_min_slope:
                guard.min_hp_slope_db = max(guard.min_hp_slope_db, int(lim.hp_min_slope))
        if need:
            guard.min_hp_hz = max(guard.min_hp_hz or 0, need)
            if rp:
                guard.min_hp_slope_db = max(guard.min_hp_slope_db, rp.min_hp_slope_db)
        guard.fs_factor = factor
    return OutputProtections.model_validate(result.model_dump())


def check(tune: Tune, policy: SafetyPolicy, previous: Tune | None = None, driver_limits: dict | None = None,
          protections: OutputProtections | None = None, unmute_levels: dict[str, float] | None = None) -> list[str]:
    """driver_limits: channel -> equipment.DriverLimits from recorded driver specs.
    unmute_levels: output -> the level it was playing at when muted (same connection and
    routing); unmuting at or below it is a return to a known state, not a jump."""
    problems: list[str] = []
    effective = tighten_outputs(tune, policy, protections, driver_limits)
    if tune.master_gain_db > policy.max_master_gain_db:
        problems.append(f"master gain {tune.master_gain_db} dB exceeds {policy.max_master_gain_db} dB")
    for ch in tune.channels:
        if ch.gain_db > policy.max_channel_gain_db:
            problems.append(f"{ch.id}: gain {ch.gain_db} dB exceeds {policy.max_channel_gain_db} dB")
        for i, b in enumerate(ch.eq):
            if b.enabled and b.gain_db > policy.max_eq_boost_db:
                problems.append(f"{ch.id} band {i + 1}: boost {b.gain_db} dB exceeds {policy.max_eq_boost_db} dB")
        if not ch.mute:
            peak, at = _peak_response(ch)
            if peak > policy.max_total_boost_db + _TOL:
                problems.append(f"{ch.id}: EQ and gain combine to {peak:+.1f} dB at {at:.0f} Hz, above the "
                                f"{policy.max_total_boost_db:+g} dB limit for one output")
        guard = effective.outputs[ch.id]
        if guard.min_hp_hz is not None and not ch.mute:
            if ch.hp is None:
                problems.append(f"{ch.id}: high-pass filter required (>= {guard.min_hp_hz:g} Hz, physical output)")
            else:
                if ch.hp.freq_hz < guard.min_hp_hz:
                    problems.append(f"{ch.id}: high-pass {ch.hp.freq_hz:g} Hz below minimum {guard.min_hp_hz:g} Hz (physical output)")
                if ch.hp.slope_db < guard.min_hp_slope_db:
                    problems.append(f"{ch.id}: high-pass slope {ch.hp.slope_db} dB/oct below {guard.min_hp_slope_db} (physical output)")
        if guard.max_lp_hz and not ch.mute and (ch.lp is None or ch.lp.freq_hz > guard.max_lp_hz):
            have = f"{ch.lp.freq_hz:g} Hz" if ch.lp else "none"
            problems.append(f"{ch.id}: low-pass {have} is above the physical output maximum {guard.max_lp_hz:g} Hz")
    if previous is not None:
        problems += _step_limits(tune, previous, policy, unmute_levels or {})
    return problems


def advisories(tune: Tune, policy: SafetyPolicy, driver_limits: dict | None = None,
               protections: OutputProtections | None = None,
               advisory_protections: OutputProtections | None = None) -> list[str]:
    """Yellow tier: allowed settings below a recommended (not enforced) high-pass margin.
    Red-tier problems come from check(); a channel that fails those is not repeated here."""
    hard = tighten_outputs(tune, policy, protections, driver_limits)
    soft = tighten_outputs(tune, policy, advisory_protections or protections, driver_limits, advisory=True)
    out = []
    for ch in tune.channels:
        floor, margin = hard.outputs[ch.id].min_hp_hz or 0, soft.outputs[ch.id].min_hp_hz or 0
        if ch.mute or ch.hp is None or margin <= floor:
            continue
        if floor <= ch.hp.freq_hz < margin:
            out.append(f"{ch.id}: high-pass {ch.hp.freq_hz:g} Hz is below the recommended {margin:g} Hz margin "
                       f"(Fs multiple); allowed down to the manufacturer minimum {floor:g} Hz")
    return out


def _step_limits(new: Tune, old: Tune, policy: SafetyPolicy, unmute_levels: dict[str, float]) -> list[str]:
    out = []
    lim = policy.max_boost_step_db
    if new.master_gain_db - old.master_gain_db > lim:
        out.append(f"master gain raised by {new.master_gain_db - old.master_gain_db:.1f} dB in one step (max {lim})")
    for n in new.channels:
        o = old.channel(n.id)
        before_channel = len(out)
        if n.gain_db - o.gain_db > lim:
            out.append(f"{n.id}: gain raised by {n.gain_db - o.gain_db:.1f} dB in one step (max {lim})")
        if o.mute and not n.mute and n.gain_db > 0:
            before = unmute_levels.get(n.id)
            if before is None:
                out.append(f"{n.id}: unmuting with positive gain and no remembered level from before the mute; "
                           "unmute at 0 dB first")
            elif n.gain_db > before:
                out.append(f"{n.id}: unmuting at {n.gain_db:+g} dB, above the {before:+g} dB it played at when "
                           "muted; unmute at 0 dB first")
        for i, (nb, ob) in enumerate(zip(n.eq, o.eq)):
            nboost = nb.gain_db if nb.enabled else 0.0
            oboost = ob.gain_db if ob.enabled else 0.0
            if nboost - max(oboost, 0.0) > lim and nboost > 0:
                out.append(f"{n.id} band {i + 1}: boost raised by {nboost - max(oboost, 0):.1f} dB in one step (max {lim})")
        if len(out) == before_channel and not n.mute:
            rise, at = _largest_rise(o, n)
            if rise > lim + _TOL:
                out.append(f"{n.id}: output raised by {rise:.1f} dB at {at:.0f} Hz in one step (max {lim}); "
                           "several smaller changes add up at the same frequency")
    return out


_TOL = 0.05  # dB; filter maths rounding, not a margin


def _grid(*channels):
    """Log grid over the audio band plus every enabled EQ centre, so narrow peaks are not missed."""
    import numpy as np

    centres = [b.freq_hz for ch in channels for b in ch.eq if b.enabled and 10 <= b.freq_hz <= 24000]
    return np.unique(np.concatenate([np.geomspace(10, 24000, 600), np.asarray(centres, dtype=float)]))


def _response(ch, freqs, crossovers: bool = True):
    """Predicted output magnitude with the mute ignored (mutes are checked separately).
    crossovers=False gives EQ + gain only: crossover moves are governed by the high-pass floors."""
    from .mapping import channel_response
    from .model import SAMPLE_RATE

    update = {"mute": False} if crossovers else {"mute": False, "hp": None, "lp": None}
    return channel_response(ch.model_copy(update=update), SAMPLE_RATE, freqs)


def _peak_response(ch) -> tuple[float, float]:
    freqs = _grid(ch)
    db = _response(ch, freqs)
    i = int(db.argmax())
    return float(db[i]), float(freqs[i])


def _largest_rise(old, new) -> tuple[float, float]:
    freqs = _grid(old, new)
    rise = _response(new, freqs, crossovers=False) - _response(old, freqs, crossovers=False)
    i = int(rise.argmax())
    return float(rise[i]), float(freqs[i])
