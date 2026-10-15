"""Hard limits that protect speakers. Checked before anything reaches the DSP.

Agents and the UI go through the same checks; there is no bypass flag in the API.
Edit the policy (saved alongside the tune) to change limits deliberately.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .model import Role, Tune


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


def check(tune: Tune, policy: SafetyPolicy, previous: Tune | None = None, driver_limits: dict | None = None) -> list[str]:
    """driver_limits: channel -> equipment.DriverLimits from recorded driver specs."""
    problems: list[str] = []
    for cid, lim in (driver_limits or {}).items():
        try:
            ch = tune.channel(cid)
        except KeyError:
            continue
        if ch.mute or ch.role is Role.UNUSED:
            continue
        rp = policy.roles.get(ch.role)
        need, why = 0.0, []
        if lim.fs and rp and rp.fs_factor:
            need, why = rp.fs_factor * lim.fs, [f"{rp.fs_factor:g}×Fs {lim.fs:g} Hz"]
        if lim.hp_min and lim.hp_min >= need:
            need, why = lim.hp_min, [f"manufacturer minimum {lim.hp_min:g} Hz"]
        if need:
            if ch.hp is None or ch.hp.freq_hz < round(need):
                have = f"{ch.hp.freq_hz:g} Hz" if ch.hp else "none"
                problems.append(f"{cid}: high-pass {have} is below {round(need)} Hz ({why[0]}, {lim.label})")
            elif lim.hp_min_slope and ch.hp.slope_db < lim.hp_min_slope:
                problems.append(f"{cid}: high-pass slope {ch.hp.slope_db} dB/oct is below the manufacturer's "
                                f"{lim.hp_min_slope:g} dB/oct ({lim.label})")
        if lim.lp_max and (ch.lp is None or ch.lp.freq_hz > lim.lp_max):
            have = f"{ch.lp.freq_hz:g} Hz" if ch.lp else "none"
            problems.append(f"{cid}: low-pass {have} is above the manufacturer maximum {lim.lp_max:g} Hz ({lim.label})")
    if tune.master_gain_db > policy.max_master_gain_db:
        problems.append(f"master gain {tune.master_gain_db} dB exceeds {policy.max_master_gain_db} dB")
    for ch in tune.channels:
        if ch.role is Role.UNUSED:
            continue
        if ch.gain_db > policy.max_channel_gain_db:
            problems.append(f"{ch.id}: gain {ch.gain_db} dB exceeds {policy.max_channel_gain_db} dB")
        for i, b in enumerate(ch.eq):
            if b.enabled and b.gain_db > policy.max_eq_boost_db:
                problems.append(f"{ch.id} band {i + 1}: boost {b.gain_db} dB exceeds {policy.max_eq_boost_db} dB")
        rp = policy.roles.get(ch.role)
        if rp and rp.min_hp_hz is not None and not ch.mute:
            if ch.hp is None:
                problems.append(f"{ch.id} ({ch.role.value}): high-pass filter required (>= {rp.min_hp_hz} Hz)")
            else:
                if ch.hp.freq_hz < rp.min_hp_hz:
                    problems.append(f"{ch.id} ({ch.role.value}): high-pass {ch.hp.freq_hz} Hz below minimum {rp.min_hp_hz} Hz")
                if ch.hp.slope_db < rp.min_hp_slope_db:
                    problems.append(f"{ch.id} ({ch.role.value}): high-pass slope {ch.hp.slope_db} dB/oct below {rp.min_hp_slope_db}")
    if previous is not None:
        problems += _step_limits(tune, previous, policy)
    return problems


def _step_limits(new: Tune, old: Tune, policy: SafetyPolicy) -> list[str]:
    out = []
    lim = policy.max_boost_step_db
    if new.master_gain_db - old.master_gain_db > lim:
        out.append(f"master gain raised by {new.master_gain_db - old.master_gain_db:.1f} dB in one step (max {lim})")
    for n, o in zip(new.channels, old.channels):
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
