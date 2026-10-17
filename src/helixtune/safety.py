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

    The Fs-multiple margin is enforced only for drivers without a manufacturer minimum
    high-pass; where the manufacturer publishes one, that figure is the enforced (red)
    floor and the margin is the advisory (yellow) floor, included when advisory=True."""
    result = (existing or OutputProtections()).model_copy(deep=True)
    for ch in tune.channels:
        guard = result.outputs[ch.id]
        rp = policy.roles.get(ch.role)
        need = rp.min_hp_hz if rp else None
        factor = max(guard.fs_factor, (rp.fs_factor or 0) if rp else 0)
        lim = (driver_limits or {}).get(ch.id)
        if lim:
            fs_margin = factor * lim.fs if lim.fs and factor else None
            if lim.hp_min and not advisory:
                fs_margin = None
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
          protections: OutputProtections | None = None) -> list[str]:
    """driver_limits: channel -> equipment.DriverLimits from recorded driver specs."""
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
        problems += _step_limits(tune, previous, policy)
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


def _step_limits(new: Tune, old: Tune, policy: SafetyPolicy) -> list[str]:
    out = []
    lim = policy.max_boost_step_db
    if new.master_gain_db - old.master_gain_db > lim:
        out.append(f"master gain raised by {new.master_gain_db - old.master_gain_db:.1f} dB in one step (max {lim})")
    for n in new.channels:
        o = old.channel(n.id)
        if n.gain_db - o.gain_db > lim:
            out.append(f"{n.id}: gain raised by {n.gain_db - o.gain_db:.1f} dB in one step (max {lim})")
        if o.mute and not n.mute and n.gain_db > 0:
            out.append(f"{n.id}: unmuting with positive gain; set gain <= 0 dB first")
        for i, (nb, ob) in enumerate(zip(n.eq, o.eq)):
            nboost = nb.gain_db if nb.enabled else 0.0
            oboost = ob.gain_db if ob.enabled else 0.0
            if nboost - max(oboost, 0.0) > lim and nboost > 0:
                out.append(f"{n.id} band {i + 1}: boost raised by {nboost - max(oboost, 0):.1f} dB in one step (max {lim})")
    return out
