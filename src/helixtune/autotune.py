"""Automatic tuning proposals: EQ to target, levels, and time alignment from distances.

Everything here only *computes* proposals. Nothing is applied without review, and the
engine's safety policy still checks the result when it is applied.
"""

from __future__ import annotations

import math

import numpy as np

from . import measurements as M
from .dsp import filters as F
from .model import EQ_BANDS, Channel, EqBand, Role, Tune
from .proposals import Edit, Proposal

SPEED_OF_SOUND = 343.0  # m/s

# ---- EQ to target -----------------------------------------------------------------------


def _peak_db(f0: float, g: float, q: float, fs: float, grid: np.ndarray) -> np.ndarray:
    bq = F.eq_biquad(F.EqType.PEAK, f0, g, q, fs)
    return 20 * np.log10(np.maximum(np.abs(bq.response(grid, fs)), 1e-9))


def _q_limit(f: float) -> float:
    # narrow corrections are position-dependent at higher frequencies in a car
    return 8.0 if f < 300 else 5.0 if f < 2000 else 3.0


def _passband(ch: Channel, fmax: float) -> tuple[float, float]:
    lo = max(25.0, ch.hp.freq_hz * 1.25 if ch.hp else 25.0)
    hi = min(fmax, ch.lp.freq_hz / 1.25 if ch.lp else 16000.0)
    return lo, hi


def fit_eq(base_db: np.ndarray, target_db: np.ndarray, grid: np.ndarray, lo: float, hi: float, fs: float,
           max_bands: int, max_boost: float, max_cut: float = 12.0, tol: float = 1.5
           ) -> tuple[list[tuple[float, float, float]], dict]:
    """Greedy PEQ fit of base_db toward target_db within [lo, hi]. Returns bands + metrics.

    The target is level-matched to the response inside the band, so this corrects shape,
    not level. Peaks (excess) are cut; dips are only partly filled and boosts are capped,
    since in-car dips are often cancellations that boost cannot fix.
    """
    mask = (grid >= lo) & (grid <= hi)
    if mask.sum() < 8:
        return [], {"rms_before": 0.0, "rms_after": 0.0, "max_before": 0.0, "max_after": 0.0}
    tgt = target_db + (base_db[mask] - target_db[mask]).mean()
    eq = np.zeros_like(grid)
    bands: list[tuple[float, float, float]] = []

    def resid(e):
        r = (base_db + e - tgt)[mask]
        return r - r.mean()  # shape only: level is the levels step's job

    def cost(e):
        r = resid(e)
        return float(np.sqrt(np.mean(r ** 2)))

    before = resid(eq)
    for _ in range(max_bands):
        r = base_db + eq - tgt
        r = r - r[mask].mean()
        score = np.where(r > 0, r, 0.5 * r)          # prefer cutting peaks over filling dips
        score = np.where(mask, np.abs(score), 0)
        i = int(np.argmax(score))
        if abs(r[i]) < tol:
            break
        f0 = float(grid[i])
        g = float(np.clip(-r[i] * (1.0 if r[i] > 0 else 0.6), -max_cut, max_boost))
        near = next((n for n, b in enumerate(bands) if abs(math.log2(b[0] / f0)) < 1 / 6), None)
        if near is not None:
            # refit the nearby band rather than stacking a second one on top of it
            fb, gb, qb = bands.pop(near)
            eq = eq - _peak_db(fb, gb, qb, fs, grid)
            f0, g = fb, float(np.clip(gb + g, -max_cut, max_boost))
        half = abs(r[i]) / 2
        j = i
        while j > 0 and mask[j - 1] and np.sign(r[j - 1]) == np.sign(r[i]) and abs(r[j - 1]) > half:
            j -= 1
        k = i
        while k < len(grid) - 1 and mask[k + 1] and np.sign(r[k + 1]) == np.sign(r[i]) and abs(r[k + 1]) > half:
            k += 1
        bw = max(math.log2(grid[k] / grid[j]), 1 / 12)
        q = float(np.clip(math.sqrt(2 ** bw) / (2 ** bw - 1), 0.5, _q_limit(f0)))
        # local refinement
        best = (f0, g, q)
        best_c = cost(eq + _peak_db(f0, g, q, fs, grid))
        for _ in range(4):
            improved = False
            for df, dg, dq in ((2 ** (1 / 24), 0, 1), (2 ** (-1 / 24), 0, 1), (1, 0.5, 1), (1, -0.5, 1),
                               (1, 0, 1.15), (1, 0, 1 / 1.15)):
                cf, cg, cq = best[0] * df, float(np.clip(best[1] + dg, -max_cut, max_boost)), \
                    float(np.clip(best[2] * dq, 0.5, _q_limit(best[0] * df)))
                if not lo <= cf <= hi:
                    continue
                c = cost(eq + _peak_db(cf, cg, cq, fs, grid))
                if c < best_c - 1e-4:
                    best, best_c, improved = (cf, cg, cq), c, True
            if not improved:
                break
        if best_c >= cost(eq) - 0.05:
            break  # no meaningful improvement left
        eq = eq + _peak_db(*best, fs, grid)
        bands.append((round(best[0]), round(best[1] * 4) / 4, round(best[2], 2)))
    after = resid(eq)
    return bands, {"rms_before": round(float(np.sqrt(np.mean(before ** 2))), 2),
                   "rms_after": round(float(np.sqrt(np.mean(after ** 2))), 2),
                   "max_before": round(float(np.max(np.abs(before))), 2),
                   "max_after": round(float(np.max(np.abs(after))), 2),
                   "band_hz": [round(lo), round(hi)]}


def propose_auto_eq(tune: Tune, meas: dict[str, M.Measurement], target_db: np.ndarray, channels: list[str],
                    max_bands: int = 8, max_freq: float = 8000, max_boost: float = 3.0,
                    replace: bool = True) -> Proposal:
    grid = M.GRID
    fs = tune.sample_rate
    edits, notes, metrics = [], [], {}
    done: set[str] = set()
    for cid in channels:
        if cid in done:
            continue
        m = meas.get(cid)
        ch = tune.channel(cid)
        if m is None or m.tune is None:
            notes.append(f"{cid}: no measurement with a known tune; skipped")
            continue
        # a measurement of several channels together (e.g. both subs) gets one linked EQ
        group = list(m.channels) or [cid]  # whole measured group, even if only one was requested
        done.update(group)
        noeq = tune.model_copy(deep=True)
        if replace:
            for c in group:
                for b in noeq.channel(c).eq:
                    b.enabled = False
        base = M.smooth(M.predict(m, noeq, grid), grid, 6)
        lo, hi = _passband(ch, max_freq)
        existing = [] if replace else [b for b in ch.eq if b.enabled]
        budget = min(max_bands, EQ_BANDS - len(existing))
        bands, met = fit_eq(base, target_db, grid, lo, hi, fs, budget, max_boost)
        gid = "+".join(group)
        metrics[gid] = met
        if not bands:
            notes.append(f"{gid}: already within ±1.5 dB of target shape in {met.get('band_hz')} Hz")
            continue
        bands.sort()
        desc = ", ".join(f"{f} Hz {g:+.1f} dB Q{q}" for f, g, q in bands)
        for c in group:
            cch = tune.channel(c)
            new = [b.model_copy() for b in cch.eq] if not replace else [EqBand(freq_hz=b.freq_hz) for b in cch.eq]
            free = [i for i, b in enumerate(new) if not b.enabled]
            for (f, g, q), i in zip(bands, free):
                new[i] = EqBand(enabled=True, type=F.EqType.PEAK, freq_hz=f, gain_db=g, q=q)
            edits.append(Edit(channel=c, field="eq", value=[b.model_dump() for b in new],
                              before=[b.model_dump() for b in cch.eq],
                              label=f"{c} {cch.name or cch.role.value}: {len(bands)} bands ({desc}); "
                                    f"error RMS {met['rms_before']} → {met['rms_after']} dB"
                                    + (f" [linked with {', '.join(x for x in group if x != c)}]" if len(group) > 1 else "")))
    return Proposal(kind="auto_eq", title=f"EQ to target ({', '.join(channels)})", edits=edits, notes=notes,
                    metrics=metrics)


# ---- levels ---------------------------------------------------------------------------------

def propose_levels(tune: Tune, meas: dict[str, M.Measurement], target_db: np.ndarray, max_step: float = 3.0
                   ) -> Proposal:
    """Match each driver's in-band level to the target (level-matched to the whole system)."""
    grid = M.GRID
    edits, notes = [], []
    for ch in tune.channels:
        m = meas.get(ch.id)
        if ch.role is Role.UNUSED or m is None or m.tune is None:
            continue
        pred = M.smooth(M.predict(m, tune, grid), grid, 3)
        lo, hi = _passband(ch, 16000)
        mask = (grid >= lo) & (grid <= hi)
        if mask.sum() < 4:
            continue
        diff = float((target_db[mask] - pred[mask]).mean())
        step = float(np.clip(diff, -max_step, max_step))
        if abs(step) < 0.5:
            continue
        new = round((ch.gain_db + step) * 2) / 2
        lbl = f"{ch.id} {ch.name or ch.role.value}: level {ch.gain_db:+.1f} → {new:+.1f} dB"
        if abs(diff) > max_step:
            lbl += f" (wants {diff:+.1f}; limited to ±{max_step} per step)"
        edits.append(Edit(channel=ch.id, field="gain_db", value=new, before=ch.gain_db, label=lbl))
    if not edits:
        notes.append("All measured drivers are within 0.5 dB of target level.")
    return Proposal(kind="levels", title="Match driver levels to target", edits=edits, notes=notes)


# ---- time alignment from distances --------------------------------------------------------

def propose_alignment(tune: Tune, distances_cm: dict[str, float]) -> Proposal:
    """Delay every driver so all arrive with the farthest one (tape-measure method)."""
    used = {cid.upper(): d for cid, d in distances_cm.items() if d is not None and d > 0}
    if not used:
        return Proposal(kind="alignment", title="Time alignment", edits=[], notes=["No distances given."])
    far = max(used.values())
    edits = []
    for cid, d in sorted(used.items()):
        ch = tune.channel(cid)
        ms = round((far - d) / 100 / SPEED_OF_SOUND * 1000, 3)
        if abs(ms - ch.delay_ms) < 0.005:
            continue
        edits.append(Edit(channel=cid, field="delay_ms", value=ms, before=ch.delay_ms,
                          label=f"{cid} {ch.name or ch.role.value}: {d:.1f} cm → delay {ch.delay_ms:.3f} → {ms:.3f} ms"))
    ref = max(used, key=used.get)
    return Proposal(kind="alignment", title="Time alignment from distances", edits=edits,
                    notes=[f"Reference (farthest) driver: {ref} at {far:.1f} cm; speed of sound {SPEED_OF_SOUND} m/s. "
                           "Fine-tune by ear or with impulse measurements afterwards."])
