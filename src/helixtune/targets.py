"""Target curves: built-ins plus user curves (piecewise-linear in log frequency)."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field


class Target(BaseModel):
    name: str
    description: str = ""
    points: list[tuple[float, float]] = Field(..., description="(Hz, dB) breakpoints, interpolated in log f")
    builtin: bool = False

    def at(self, freqs: np.ndarray) -> np.ndarray:
        f, db = zip(*sorted(self.points))
        return np.interp(np.log(freqs), np.log(np.asarray(f)), np.asarray(db))


def _shelf_tilt(bass_db: float, corner: float, tilt_db_oct: float, pivot: float = 1000) -> list[tuple[float, float]]:
    f = np.geomspace(10, 24000, 40)
    db = bass_db / (1 + (f / corner) ** 2) - tilt_db_oct * np.maximum(0, np.log2(f / pivot))
    return [(round(float(a), 2), round(float(b), 2)) for a, b in zip(f, db)]


BUILTINS = [
    Target(name="Flat", description="Reference: equal level at all frequencies.",
           points=[(10, 0), (24000, 0)], builtin=True),
    Target(name="Car preference", description="Bass shelf about +8 dB below ~70 Hz, gentle "
           "-0.8 dB/oct treble tilt above 1 kHz. A common in-car starting point.",
           points=_shelf_tilt(8, 70, 0.8), builtin=True),
    Target(name="Car — bass heavy", description="+11 dB bass shelf, -1 dB/oct tilt.",
           points=_shelf_tilt(11, 80, 1.0), builtin=True),
    Target(name="Gentle tilt", description="No bass shelf; -0.5 dB/oct from 1 kHz.",
           points=_shelf_tilt(0, 70, 0.5), builtin=True),
]
