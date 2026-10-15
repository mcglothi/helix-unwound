"""ADAU145x parameter number format: 32-bit two's-complement 8.24 fixed point."""

from __future__ import annotations

FRAC_BITS = 24
SCALE = 1 << FRAC_BITS
MAX = (1 << 31) - 1
MIN = -(1 << 31)


def to_824(x: float) -> int:
    v = round(x * SCALE)
    if not MIN <= v <= MAX:
        raise OverflowError(f"{x} does not fit 8.24 (range ±128)")
    return v


def from_824(v: int) -> float:
    if v & 0x80000000:
        v -= 1 << 32
    return v / SCALE


def word_824(x: float) -> bytes:
    return (to_824(x) & 0xFFFFFFFF).to_bytes(4, "big")


def word_int(n: int) -> bytes:
    return (n & 0xFFFFFFFF).to_bytes(4, "big")
