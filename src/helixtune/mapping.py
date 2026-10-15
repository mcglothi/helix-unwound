"""Tune -> DSP parameter RAM image for the HELIX DSP PRO MK2 (DSPPro2.at01).

Everything marked PROVISIONAL is a reading of SigmaStudio naming conventions that
still needs confirming against a capture of the original PC-Tool:
  - EQ block <-> channel assignment (EQ1/EQ2 = channel A, EQ1_k/EQ2_k = channel k)
  - stored biquad sign convention (SigmaStudio stores -a1, -a2)
  - crossover slot usage (7 biquad stages + 2 first-order sections, series cascade)
  - delay in integer samples, mute/invert as integer flags
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .devicefile import ParamMap
from .dsp import filters as F
from .dsp.fixed import word_824, word_int
from .model import CHANNELS, EQ_BANDS, Channel, Tune

NEGATE_A = True  # PROVISIONAL
XO_BIQUAD_SLOTS = 7
XO_FIRST_ORDER_SLOTS = 2
STAGES_PER_EQ_BLOCK = 15


class MappingError(ValueError):
    pass


@dataclass
class ChannelAddrs:
    eq: list[dict[str, int]]          # 30 x {B2,B1,B0,A2,A1}
    xo_bq: list[dict[str, int]]       # 7 x {B2,B1,B0,A2,A1}
    xo_fo: list[dict[str, int]]       # 2 x {B1,B0,A1}
    delay: int
    invert: int
    gain: int
    mute: int
    mix: dict[str, int]                # input name -> optical-matrix VOL address


def _req(pm: ParamMap, name: str) -> int:
    try:
        return pm.params[name]
    except KeyError:
        raise MappingError(f"parameter {name} missing from device map") from None


def _bq(pm, prefix) -> dict[str, int]:
    return {k: _req(pm, f"{prefix}_{k}") for k in ("B2", "B1", "B0", "A2", "A1")}


def _one(pm: ParamMap, pattern: str) -> int:
    hits = pm.find(pattern)
    if len(hits) != 1:
        raise MappingError(f"expected one parameter matching {pattern}, found {sorted(hits)}")
    return next(iter(hits.values()))


def channel_addrs(pm: ParamMap, idx: int) -> ChannelAddrs:
    cid = CHANNELS[idx]
    suffix = "" if idx == 0 else f"_{idx + 1}"
    eq = []
    for block in ("EQ1", "EQ2"):
        for s in range(STAGES_PER_EQ_BLOCK):
            eq.append(_bq(pm, f"EQUALIZER_{block}{suffix}_ALG0_STAGE{s}"))
    xo_bq = [_bq(pm, f"FILTERS__PHASE_HP2_{cid}_ALG0_STAGE{s}") for s in range(XO_BIQUAD_SLOTS)]
    xo_fo = [{k: _req(pm, f"FILTERS__PHASE_LP1_{cid}_ALG0_PARAM{k}_{n}") for k in ("B1", "B0", "A1")}
             for n in (1, 2)]
    return ChannelAddrs(
        eq=eq, xo_bq=xo_bq, xo_fo=xo_fo,
        delay=_req(pm, f"DELAY__PHASE_SWITCH_DELAY{cid}_DELAYAMT"),
        invert=_one(pm, rf"^DELAY__PHASE_SWITCH_INV{cid}_.*INVERT$"),
        gain=_one(pm, rf"^GAIN_GAIN{cid}_.*GAIN$"),
        mute=_one(pm, rf"^MUTE{cid}_.*MUTE$"),
        # PROVISIONAL: optical-input matrix VOL{out:02d}{in:02d}; matches the .afpx 2-input route layout
        mix={name: _one(pm, rf"^OPTO_MATRIX_OPTOMIXER_.*VOL{idx:02d}{n:02d}$") for n, name in enumerate(("L", "R"))},
    )


class DeviceMapping:
    def __init__(self, pm: ParamMap):
        self.pm = pm
        self.channels = [channel_addrs(pm, i) for i in range(len(CHANNELS))]
        self.master = _one(pm, r"^GAIN1_.*GAIN$")  # PROVISIONAL: GAIN1 = master

    # -- section packing ----------------------------------------------------------

    @staticmethod
    def crossover_sections(ch: Channel, fs: float) -> tuple[list[F.Biquad], list[F.FirstOrder]]:
        bqs: list[F.Biquad] = []
        fos: list[F.FirstOrder] = []
        for xo, hp in ((ch.hp, True), (ch.lp, False)):
            if xo is None:
                continue
            b, f = F.crossover_sections(xo.type, xo.slope_db, xo.freq_hz, fs, hp)
            bqs += b
            fos += f
        if len(bqs) > XO_BIQUAD_SLOTS or len(fos) > XO_FIRST_ORDER_SLOTS:
            raise MappingError(
                f"channel {ch.id}: crossover needs {len(bqs)} biquads + {len(fos)} first-order "
                f"sections; the DSP has {XO_BIQUAD_SLOTS} + {XO_FIRST_ORDER_SLOTS}. Reduce a slope.")
        return bqs, fos

    @staticmethod
    def eq_sections(ch: Channel, fs: float) -> list[F.Biquad]:
        return [F.eq_biquad(b.type, b.freq_hz, b.gain_db, b.q, fs) if b.enabled else F.Biquad.identity()
                for b in ch.eq]

    # -- rendering ----------------------------------------------------------------

    @staticmethod
    def _put_bq(img: dict[int, bytes], addrs: dict[str, int], bq: F.Biquad) -> None:
        s = -1.0 if NEGATE_A else 1.0
        vals = {"B0": bq.b0, "B1": bq.b1, "B2": bq.b2, "A1": s * bq.a1, "A2": s * bq.a2}
        for k, a in addrs.items():
            img[a] = word_824(vals[k])

    @staticmethod
    def _put_fo(img: dict[int, bytes], addrs: dict[str, int], fo: F.FirstOrder) -> None:
        s = -1.0 if NEGATE_A else 1.0
        vals = {"B0": fo.b0, "B1": fo.b1, "A1": s * fo.a1}
        for k, a in addrs.items():
            img[a] = word_824(vals[k])

    def render(self, tune: Tune) -> dict[int, bytes]:
        """Full image: param address -> 4-byte big-endian word."""
        fs = tune.sample_rate
        img: dict[int, bytes] = {}
        img[self.master] = word_824(10 ** (tune.master_gain_db / 20))
        # Physical addresses belong to output IDs, independent of client list order.
        for cid, ad in zip(CHANNELS, self.channels):
            ch = tune.channel(cid)
            for addrs, bq in zip(ad.eq, self.eq_sections(ch, fs)):
                self._put_bq(img, addrs, bq)
            bqs, fos = self.crossover_sections(ch, fs)
            bqs += [F.Biquad.identity()] * (XO_BIQUAD_SLOTS - len(bqs))
            fos += [F.FirstOrder.identity()] * (XO_FIRST_ORDER_SLOTS - len(fos))
            for addrs, bq in zip(ad.xo_bq, bqs):
                self._put_bq(img, addrs, bq)
            for addrs, fo in zip(ad.xo_fo, fos):
                self._put_fo(img, addrs, fo)
            img[ad.delay] = word_int(round(ch.delay_ms * fs / 1000))
            img[ad.invert] = word_int(1 if ch.invert else 0)
            img[ad.gain] = word_824(10 ** (ch.gain_db / 20))
            img[ad.mute] = word_int(0 if ch.mute else 1)
            for name, addr in ad.mix.items():
                img[addr] = word_824(ch.mix.get(name, 0.0))
        return img


def diff(old: dict[int, bytes] | None, new: dict[int, bytes]) -> dict[int, bytes]:
    if old is None:
        return dict(new)
    return {a: w for a, w in new.items() if old.get(a) != w}


def coalesce(changes: dict[int, bytes], max_words: int = 60) -> list[tuple[int, bytes]]:
    """Group changed words into contiguous runs -> (start_addr, data) write ops."""
    ops: list[tuple[int, bytes]] = []
    run_start, run = None, bytearray()
    for a in sorted(changes):
        if run_start is not None and a == run_start + len(run) // 4 and len(run) // 4 < max_words:
            run += changes[a]
        else:
            if run_start is not None:
                ops.append((run_start, bytes(run)))
            run_start, run = a, bytearray(changes[a])
    if run_start is not None:
        ops.append((run_start, bytes(run)))
    return ops


def channel_response(ch: Channel, fs: float, freqs):
    """Predicted magnitude (dB) of one channel's EQ + crossover + gain."""
    import numpy as np

    bqs, fos = DeviceMapping.crossover_sections(ch, fs)
    h = F.cascade_response(DeviceMapping.eq_sections(ch, fs) + bqs + fos, freqs, fs)
    db = 20 * np.log10(np.maximum(np.abs(h), 1e-12)) + ch.gain_db
    if ch.mute:
        db = np.full_like(db, -120.0)
    return db


__all__ = ["DeviceMapping", "MappingError", "diff", "coalesce", "channel_response", "EQ_BANDS", "math"]
