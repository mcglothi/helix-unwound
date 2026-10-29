"""The tune: a device-independent description of everything we control.

Pydantic models so the same schema drives the HTTP API, the MCP tools and the
saved snapshot files.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from .dsp.filters import EqType, XoType

CHANNELS = "ABCDEFGHIJ"
EQ_BANDS = 30
SAMPLE_RATE = 96000.0


class Role(str, Enum):
    TWEETER = "tweeter"
    MIDRANGE = "midrange"
    MIDBASS = "midbass"
    WOOFER = "woofer"
    SUBWOOFER = "subwoofer"
    FULLRANGE = "fullrange"
    UNUSED = "unused"


class Crossover(BaseModel):
    type: XoType = XoType.LINKWITZ_RILEY
    slope_db: int = Field(24, ge=6, le=48, multiple_of=6)
    freq_hz: float = Field(..., ge=10, le=24000)


class EqBand(BaseModel):
    enabled: bool = False
    type: EqType = EqType.PEAK
    freq_hz: float = Field(1000.0, ge=10, le=24000)
    gain_db: float = Field(0.0, ge=-24, le=24)
    q: float = Field(1.0, ge=0.1, le=30)


def _default_bands() -> list[EqBand]:
    # spread default centre frequencies log-uniformly 20 Hz..20 kHz like a graphic EQ
    import math

    return [EqBand(freq_hz=round(20 * 10 ** (3 * i / (EQ_BANDS - 1)), 1)) for i in range(EQ_BANDS)]


INPUTS = ("L", "R")  # the 2-channel digital (optical) input the PAC AmpPRO feeds


class Channel(BaseModel):
    id: str
    name: str = ""
    role: Role = Role.UNUSED
    gain_db: float = Field(0.0, ge=-60, le=12)
    mute: bool = False
    invert: bool = False
    delay_ms: float = Field(0.0, ge=0, le=20)
    hp: Crossover | None = None
    lp: Crossover | None = None
    eq: list[EqBand] = Field(default_factory=_default_bands)
    # input mix: linear gain from each source input (L, R). {"L": 0.5, "R": 0.5} = mono sum.
    mix: dict[str, float] = Field(default_factory=dict)
    # PC-Tool link group (.afpx LG); 0 = not linked. Edits to gain, mute, polarity,
    # crossovers or an EQ band copy that item to every channel in the same group,
    # as PC-Tool did in the 2026-10-17 captures. Delay is never linked.
    link_group: int = Field(0, ge=0, le=99)

    @field_validator("id")
    @classmethod
    def _physical_output(cls, value: str) -> str:
        value = value.upper()
        if value not in tuple(CHANNELS):
            raise ValueError(f"channel id must be one of {CHANNELS}")
        return value

    @field_validator("mix")
    @classmethod
    def _mix(cls, v):
        bad = [k for k in v if k not in INPUTS]
        if bad:
            raise ValueError(f"unknown input(s) {bad}; inputs are {INPUTS}")
        if any(not 0 <= g <= 1 for g in v.values()):
            raise ValueError("mix gains must be 0..1")
        return v

    @field_validator("eq")
    @classmethod
    def _thirty(cls, v):
        if len(v) != EQ_BANDS:
            raise ValueError(f"exactly {EQ_BANDS} EQ bands required")
        return v


class Tune(BaseModel):
    name: str = "untitled"
    device: str = "HELIX DSP PRO MK2"
    sample_rate: float = SAMPLE_RATE
    master_gain_db: float = Field(0.0, ge=-80, le=0)
    channels: list[Channel] = Field(default_factory=lambda: [
        Channel(id=c, mix={INPUTS[i % 2]: 1.0}) for i, c in enumerate(CHANNELS)])
    notes: str = ""

    @field_validator("sample_rate")
    @classmethod
    def _supported_sample_rate(cls, value: float) -> float:
        if value != SAMPLE_RATE:
            raise ValueError(f"HELIX DSP PRO MK2 requires sample_rate={SAMPLE_RATE:g}")
        return value

    @field_validator("channels")
    @classmethod
    def _physical_outputs(cls, channels: list[Channel]) -> list[Channel]:
        by_id = {ch.id: ch for ch in channels}
        if len(channels) != len(CHANNELS) or set(by_id) != set(CHANNELS):
            raise ValueError(f"exactly one channel for each physical output {CHANNELS} is required")
        return [by_id[cid] for cid in CHANNELS]

    @model_validator(mode="before")
    @classmethod
    def _default_routing(cls, value):
        # Only pre-routing serialized tunes omit every mix field. An explicitly
        # empty mix means Off, even when all ten outputs are intentionally off.
        if isinstance(value, dict):
            channels = value.get("channels")
            if channels and all(isinstance(ch, dict) and "mix" not in ch for ch in channels):
                routes = {cid: {INPUTS[i % 2]: 1.0} for i, cid in enumerate(CHANNELS)}
                value = {**value, "channels": [
                    {**ch, "mix": dict(routes.get(str(ch.get("id", "")).upper(), {}))} for ch in channels
                ]}
        return value

    def channel(self, cid: str) -> Channel:
        cid = cid.upper()
        for ch in self.channels:
            if ch.id == cid:
                return ch
        raise KeyError(f"no channel {cid!r}; channels are {CHANNELS}")

    def linked(self, cid: str) -> list[str]:
        """cid plus every channel sharing its link group, in output order."""
        group = self.channel(cid).link_group
        if not group:
            return [cid.upper()]
        return [ch.id for ch in self.channels if ch.link_group == group]
