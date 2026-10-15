"""Acoustic measurements and response prediction.

Each measurement keeps the tune that was active when it was taken. Because we
compute every filter ourselves, the response under any other tune is predicted as

    predicted_dB(f) = measured_dB(f) + |H_new(f)|dB - |H_then(f)|dB

for the channels that were playing. RTA (magnitude-only) data supports magnitude
prediction; summing between drivers needs phase (sweep data) and is approximated
as a power sum otherwise.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from .mapping import channel_response
from .model import Role, Tune

GRID = np.geomspace(10, 24000, 480)  # ~1/58 octave storage grid


class Measurement(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str
    kind: str = "rta"                       # rta | sweep
    channels: list[str] = Field(default_factory=list)   # channel ids that were playing
    seat: str = "driver"                    # driver | passenger | center | average
    taken_at: float = Field(default_factory=time.time)
    source: str = ""
    notes: str = ""
    freqs: list[float]
    spl: list[float]
    phase: list[float] | None = None
    tune: Tune | None = None                # tune active when measured (None = unknown)


def resample(freqs, spl, grid=GRID, smoothing_oct: float = 1 / 24) -> list[float]:
    """Power-average linear-spaced data onto a log grid with fractional-octave windows."""
    f = np.asarray(freqs, float)
    p = 10 ** (np.asarray(spl, float) / 10)
    out = []
    half = 2 ** (smoothing_oct / 2)
    for g in grid:
        m = (f >= g / half) & (f <= g * half)
        if not m.any():
            i = int(np.argmin(np.abs(f - g)))
            m = np.zeros_like(f, bool)
            m[i] = True
        out.append(round(float(10 * np.log10(p[m].mean())), 3))
    return out


def smooth(db: np.ndarray, grid: np.ndarray, octave_frac: float) -> np.ndarray:
    if octave_frac <= 0:
        return db
    p = 10 ** (db / 10)
    half = 2 ** (1 / octave_frac / 2)
    return np.array([10 * np.log10(p[(grid >= g / half) & (grid <= g * half)].mean()) for g in grid])


class Store:
    def __init__(self, root: Path):
        self.root = root / "measurements"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, m: Measurement) -> Measurement:
        (self.root / f"{m.id}.json").write_text(m.model_dump_json())
        return m

    def get(self, mid: str) -> Measurement:
        p = self.root / f"{mid}.json"
        if not p.exists():
            raise KeyError(f"no measurement {mid!r}")
        return Measurement.model_validate_json(p.read_text())

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            d = json.loads(p.read_text())
            out.append({k: d[k] for k in ("id", "name", "kind", "channels", "seat", "taken_at", "source", "notes")}
                       | {"has_tune": d.get("tune") is not None, "has_phase": d.get("phase") is not None})
        return sorted(out, key=lambda d: d["taken_at"])

    def delete(self, mid: str) -> None:
        (self.root / f"{mid}.json").unlink(missing_ok=True)


def _chain_db(tune: Tune, cids: list[str], grid: np.ndarray) -> dict[str, np.ndarray]:
    return {c: channel_response(tune.channel(c), tune.sample_rate, grid) for c in cids}


def predict(m: Measurement, now: Tune, grid: np.ndarray = GRID) -> np.ndarray:
    measured = np.interp(np.log(grid), np.log(m.freqs), m.spl)
    if m.tune is None or not m.channels:
        return measured
    then = _chain_db(m.tune, m.channels, grid)
    new = _chain_db(now, m.channels, grid)
    if len(m.channels) == 1:
        c = m.channels[0]
        return measured + np.clip(new[c], -80, 40) - np.clip(then[c], -80, 40)
    # several channels in one measurement: scale by the change in their power sum
    p_then = sum(10 ** (np.clip(v, -80, 40) / 10) for v in then.values())
    p_new = sum(10 ** (np.clip(v, -80, 40) / 10) for v in new.values())
    return measured + 10 * np.log10(p_new / p_then)


# ---- legacy REW .mdat import --------------------------------------------------------

_DRIVER = {"TW": Role.TWEETER, "MR": Role.MIDRANGE, "MB": Role.MIDBASS, "SUB": Role.SUBWOOFER, "SW": Role.SUBWOOFER}


def guess_channels(name: str, tune: Tune) -> tuple[list[str], str]:
    """'DS-TW' -> driver-side tweeter. DS = left in a left-hand-drive vehicle."""
    up = name.upper().replace("_", "-")
    side = "L" if up.startswith("DS") else "R" if up.startswith("PS") else None
    role = next((r for k, r in _DRIVER.items() if k in up.split("-") or up == k or up.startswith(k)), None)
    if role is None:
        return [], "driver"
    chans = [c for c in tune.channels if c.role is role]
    if side and role is not Role.SUBWOOFER:
        chans = [c for c in chans if f" {side} " in f" {c.name} "]
    return [c.id for c in chans], "driver"


def import_mdat(path: str | Path, tune_at_time: Tune | None) -> list[Measurement]:
    import javaobj.v2 as j

    def fields(o):
        return {fd.name: v for _, fs in getattr(o, "field_data", {}).items() for fd, v in fs.items()}

    def arr(v):
        return list(v.data) if hasattr(v, "data") else list(v) if isinstance(v, (list, tuple)) else None

    with open(path, "rb") as fh:
        objs = j.load(fh)
    out = []
    for o in objs:
        cd = getattr(o, "classdesc", None)
        if cd is None or cd.name != "roomeqwizard.MeasData":
            continue
        F = fields(o)
        spl = arr(F.get("splValues"))
        if not spl:
            continue
        if F.get("isLogSpaced"):
            raise ValueError("log-spaced .mdat data not supported yet")
        freqs = F["startFreq"] + np.arange(len(spl)) * F["freqStep"]
        name = str(F.get("shortDesc") or f"measurement {len(out) + 1}")
        kind = "rta" if "spectrum" in str(F.get("measNotes", "")) else "sweep"
        if kind == "rta":
            # FFT bins are power per Hz; convert to constant-percentage bands so pink
            # noise through a flat system reads flat (as REW's octave-banded RTA shows it)
            spl = list(np.asarray(spl) + 10 * np.log10(np.maximum(freqs, 1e-3) / 1000))
        chans, seat = guess_channels(name, tune_at_time) if tune_at_time else ([], "driver")
        out.append(Measurement(
            name=name, kind=kind,
            channels=chans, seat=seat, taken_at=F.get("sourceFileDate", 0) / 1000,
            source=f"{Path(path).name} (REW {F.get('rewVersion', '?')})",
            notes=str(F.get("measNotes", "")).strip(),
            freqs=GRID.round(3).tolist(), spl=resample(freqs, spl), tune=tune_at_time))
    return out
