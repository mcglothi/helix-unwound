"""Filter design: parametric EQ biquads (RBJ cookbook) and crossover cascades.

All sections are normalised (a0 = 1) and returned in textbook sign convention:
  H(z) = (b0 + b1 z^-1 + b2 z^-2) / (1 + a1 z^-1 + a2 z^-2)
Conversion to the DSP's stored sign convention happens in the mapping layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np


@dataclass(frozen=True)
class Biquad:
    b0: float
    b1: float
    b2: float
    a1: float
    a2: float

    @staticmethod
    def identity() -> "Biquad":
        return Biquad(1.0, 0.0, 0.0, 0.0, 0.0)

    def response(self, freqs: np.ndarray, fs: float) -> np.ndarray:
        z1 = np.exp(-1j * 2 * np.pi * freqs / fs)
        z2 = z1 * z1
        return (self.b0 + self.b1 * z1 + self.b2 * z2) / (1 + self.a1 * z1 + self.a2 * z2)


@dataclass(frozen=True)
class FirstOrder:
    b0: float
    b1: float
    a1: float

    @staticmethod
    def identity() -> "FirstOrder":
        return FirstOrder(1.0, 0.0, 0.0)

    def response(self, freqs: np.ndarray, fs: float) -> np.ndarray:
        z1 = np.exp(-1j * 2 * np.pi * freqs / fs)
        return (self.b0 + self.b1 * z1) / (1 + self.a1 * z1)


def _norm(b0, b1, b2, a0, a1, a2) -> Biquad:
    return Biquad(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


# ---- parametric EQ -------------------------------------------------------------

class EqType(str, Enum):
    PEAK = "peak"
    LOW_SHELF = "low_shelf"
    HIGH_SHELF = "high_shelf"
    NOTCH = "notch"
    ALLPASS = "allpass"


def eq_biquad(kind: EqType, f0: float, gain_db: float, q: float, fs: float) -> Biquad:
    if gain_db == 0 and kind in (EqType.PEAK, EqType.LOW_SHELF, EqType.HIGH_SHELF):
        return Biquad.identity()
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f0 / fs
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if kind is EqType.PEAK:
        return _norm(1 + alpha * A, -2 * cw, 1 - alpha * A, 1 + alpha / A, -2 * cw, 1 - alpha / A)
    if kind is EqType.NOTCH:
        return _norm(1, -2 * cw, 1, 1 + alpha, -2 * cw, 1 - alpha)
    if kind is EqType.ALLPASS:
        return _norm(1 - alpha, -2 * cw, 1 + alpha, 1 + alpha, -2 * cw, 1 - alpha)
    sa = 2 * math.sqrt(A) * alpha
    if kind is EqType.LOW_SHELF:
        return _norm(A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw),
                     A * ((A + 1) - (A - 1) * cw - sa), (A + 1) + (A - 1) * cw + sa,
                     -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa)
    if kind is EqType.HIGH_SHELF:
        return _norm(A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw),
                     A * ((A + 1) + (A - 1) * cw - sa), (A + 1) - (A - 1) * cw + sa,
                     2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa)
    raise ValueError(kind)


# ---- crossovers ----------------------------------------------------------------

class XoType(str, Enum):
    BUTTERWORTH = "butterworth"
    LINKWITZ_RILEY = "linkwitz_riley"
    BESSEL = "bessel"


# Bessel (phase-normalised) pole Qs and frequency scale factors per order.
_BESSEL = {
    2: [(0.5773, 1.2736)],
    3: [(0.6910, 1.4524)],  # + first-order section at 1.3270
    4: [(0.5219, 1.4192), (0.8055, 1.5912)],
    5: [(0.5635, 1.5611), (0.9165, 1.7607)],
    6: [(0.5103, 1.6060), (0.6112, 1.6913), (1.0234, 1.9071)],
    7: [(0.5324, 1.7174), (0.6608, 1.8235), (1.1262, 2.0507)],
    8: [(0.5060, 1.7837), (0.5596, 1.8376), (0.7109, 1.9591), (1.2258, 2.1953)],
}
_BESSEL_FIRST = {3: 1.3270, 5: 1.5069, 7: 1.6853}


def _butter_qs(order: int) -> list[float]:
    # pole angles theta_k = pi(2k+n-1)/(2n), k = 1..n//2; Q = -1/(2 cos theta)
    return [-1 / (2 * math.cos(math.pi * (2 * k + order - 1) / (2 * order))) for k in range(1, order // 2 + 1)]


def _hp2(fc, q, fs):
    w0 = 2 * math.pi * fc / fs
    cw, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    return _norm((1 + cw) / 2, -(1 + cw), (1 + cw) / 2, 1 + alpha, -2 * cw, 1 - alpha)


def _lp2(fc, q, fs):
    w0 = 2 * math.pi * fc / fs
    cw, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    return _norm((1 - cw) / 2, 1 - cw, (1 - cw) / 2, 1 + alpha, -2 * cw, 1 - alpha)


def _first(fc, fs, highpass: bool) -> FirstOrder:
    k = math.tan(math.pi * fc / fs)
    a1 = (k - 1) / (k + 1)
    if highpass:
        return FirstOrder(1 / (k + 1), -1 / (k + 1), a1)
    return FirstOrder(k / (k + 1), k / (k + 1), a1)


def crossover_sections(kind: XoType, slope_db: int, fc: float, fs: float, highpass: bool, *, pc_tool_q: bool = False
                       ) -> tuple[list[Biquad], list[FirstOrder]]:
    """Return (biquads, first_order_sections) for one HP or LP filter."""
    if slope_db % 6 or not 6 <= slope_db <= 48:
        raise ValueError("slope must be 6..48 dB/oct in 6 dB steps")
    order = slope_db // 6
    sec = _hp2 if highpass else _lp2
    bqs: list[Biquad] = []
    fos: list[FirstOrder] = []
    # The two-pole Butterworth kernel in captured PC-Tool LR24 uses .707,
    # not exact sqrt(.5). Keep generic analytical filters ideal by default.
    def qs(n):
        return [0.707] if pc_tool_q and n == 2 else _butter_qs(n)
    if kind is XoType.LINKWITZ_RILEY:
        if order % 2:
            raise ValueError("Linkwitz-Riley needs an even order (12/24/36/48 dB)")
        half = order // 2
        for _ in range(2):
            for q in qs(half):
                bqs.append(sec(fc, q, fs))
            if half % 2:
                fos.append(_first(fc, fs, highpass))
        # two first-order Butterworths cascade = one 2nd-order section with Q 0.5
        if len(fos) == 2:
            fos = []
            bqs.append(sec(fc, 0.5, fs))
        return bqs, fos
    if kind is XoType.BUTTERWORTH:
        # Captured 2026-10-18: PC-Tool's Butterworth 12 dB uses Q 0.71 (bit-exact), while its
        # LR24 halves use .707. Higher Butterworth orders are not yet captured cleanly.
        for q in ([0.71] if pc_tool_q and order == 2 else qs(order)):
            bqs.append(sec(fc, q, fs))
        if order % 2:
            fos.append(_first(fc, fs, highpass))
        return bqs, fos
    if kind is XoType.BESSEL:
        if order == 1:
            return [], [_first(fc, fs, highpass)]
        for q, scale in _BESSEL[order]:
            f = fc / scale if highpass else fc * scale
            bqs.append(sec(f, q, fs))
        if order in _BESSEL_FIRST:
            s = _BESSEL_FIRST[order]
            fos.append(_first(fc / s if highpass else fc * s, fs, highpass))
        return bqs, fos
    raise ValueError(kind)


def cascade_response(sections, freqs: np.ndarray, fs: float) -> np.ndarray:
    h = np.ones_like(freqs, dtype=complex)
    for s in sections:
        h *= s.response(freqs, fs)
    return h


def log_freqs(n: int = 256, lo: float = 10.0, hi: float = 24000.0) -> np.ndarray:
    return np.geomspace(lo, hi, n)
