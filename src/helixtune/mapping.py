"""Tune -> DSP parameter RAM image for the HELIX DSP PRO MK2 (DSPPro2.at01).

Everything marked PROVISIONAL is a reading of SigmaStudio naming conventions that
still needs confirming against a capture of the original PC-Tool:
  - EQ block <-> channel assignment (EQ1/EQ2 = channel A, EQ1_k/EQ2_k = channel k)
  - stored biquad sign convention (SigmaStudio stores -a1, -a2)
  - remaining slope variants beyond captured HP/LP LR12/LR24; fixed HP0..2, LP3..5 layout now follows captures
  - delay in integer samples, mute/invert as integer flags
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .devicefile import ParamMap
from .dsp import filters as F
from .dsp.fixed import word_824, word_int
from .model import CHANNELS, EQ_BANDS, Channel, Tune

NEGATE_A = True  # captured coefficient storage negates A1/A2
XO_BIQUAD_SLOTS = 7
XO_FIRST_ORDER_SLOTS = 2
STAGES_PER_EQ_BLOCK = 15
MAIN_MATRIX_INPUTS = 12
MIX_INPUTS = ("L", "R")   # main-matrix inputs 0/1 (Digital In L/R); other inputs render as 0


# Director/remote (URC) volume parameters and their slew settings. The remote owns these;
# HelixTune never writes them. 2026-10-18: Digital (optical) Volume was found at minimum with
# no captured write explaining it, so the engine refuses any write that touches this set.
PROTECTED_PATTERN = (r"^URC_FUNCTION_(MASTER|SUB|OPTO|AUX)VOLUME"
                     r"|VOLUMEURC_SLEW_MODE$|^MASTERVOLUME(OPTOOUT)?_SLEW_MODE$")


# Filter combinations whose rendered words matched PC-Tool's captured writes bit-exactly
# (2026-10-17/18). Writes to a real DSP are limited to these; emulator/offline modelling keeps
# every type. Known mismatches: Bessel and LR36 (capture 23). Everything else is uncaptured.
PHYSICAL_VERIFIED_XO = {
    "hp": {(F.XoType.LINKWITZ_RILEY, 12), (F.XoType.LINKWITZ_RILEY, 24),
           (F.XoType.BUTTERWORTH, 6), (F.XoType.BUTTERWORTH, 12), (F.XoType.BUTTERWORTH, 18)},
    "lp": {(F.XoType.LINKWITZ_RILEY, 12), (F.XoType.LINKWITZ_RILEY, 24)},
}
PHYSICAL_VERIFIED_EQ = {F.EqType.PEAK}


def physical_problems(tune: Tune) -> list[str]:
    """Settings that may not be written to a real DSP because PC-Tool's encoding is unverified."""
    out: list[str] = []
    for ch in tune.channels:
        for label, xo in (("hp", ch.hp), ("lp", ch.lp)):
            if xo is not None and (xo.type, xo.slope_db) not in PHYSICAL_VERIFIED_XO[label]:
                out.append(f"{ch.id} {label.upper()} {xo.type.value} {xo.slope_db} dB/oct is not verified against PC-Tool")
        for n, band in enumerate(ch.eq, 1):
            if band.enabled and band.type not in PHYSICAL_VERIFIED_EQ:
                out.append(f"{ch.id} EQ band {n} type {band.type.value} is not verified against PC-Tool")
    return out


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
        # Captures 23/24 (2026-10-18): PC-Tool's routing edits on either IO tab write the main
        # matrix row VOL{out:02d}{in:02d}, inputs 00/01 = Digital In L/R, and zero the other 10
        # inputs of the row. The 2-input OPTO_MATRIX is never written live.
        mix={(MIX_INPUTS[n] if n < len(MIX_INPUTS) else f"in{n}"): _one(pm, rf"^MAINMATRIX_.*VOL{idx:02d}{n:02d}$")
             for n in range(MAIN_MATRIX_INPUTS)},
    )


class DeviceMapping:
    protected: frozenset[int] = frozenset()

    @property
    def provisional(self) -> frozenset[int]:
        """Rendered for the emulator but never written to a real DSP: GAIN1's role as master
        gain is a naming guess, not captured."""
        return frozenset({self.master})

    def __init__(self, pm: ParamMap):
        self.pm = pm
        self.protected = frozenset(pm.find(PROTECTED_PATTERN).values())
        self.channels = [channel_addrs(pm, i) for i in range(len(CHANNELS))]
        self.master = _one(pm, r"^GAIN1_.*GAIN$")  # PROVISIONAL: GAIN1 = master

    # -- section packing ----------------------------------------------------------

    @staticmethod
    def crossover_sections(ch: Channel, fs: float) -> tuple[list[F.Biquad], list[F.FirstOrder]]:
        bqs: list[F.Biquad] = []
        fos: list[F.FirstOrder] = []
        for label, xo, hp in (("HP", ch.hp, True), ("LP", ch.lp, False)):
            b, f = (F.crossover_sections(xo.type, xo.slope_db, xo.freq_hz, fs, hp, pc_tool_q=True)
                    if xo is not None else ([], []))
            if len(b) > 3 or len(f) > 1:
                raise MappingError(f"channel {ch.id}: {label} exceeds the captured fixed bank of 3 biquads + 1 first-order section; this slope layout is not supported")
            bqs.extend(b + [F.Biquad.identity()] * (3 - len(b)))
            fos.append(f[0] if f else F.FirstOrder.identity())
        # Captures place HP in 0..2, LP in 3..5 and leave stage6 identity.
        return bqs + [F.Biquad.identity()], fos

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
