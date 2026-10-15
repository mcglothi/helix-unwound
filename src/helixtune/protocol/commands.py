"""Command payload builders (inner payload, before framing).

Layouts from the PC-Tool command switch FUN_00574f40. Addresses are 16-bit
big-endian. Only the commands we have a use for are built here; names for
anything beyond identify/baud are provisional until confirmed by capture.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

IDENTIFY_RESPONSE_LEN = 179  # FUN_0075db80 expects 0xb3 payload bytes
WRITE_ACK_FRAME_LEN = 10     # most write commands wait for a 10-byte reply frame


class Cmd(IntEnum):
    READ_RAM = 0x04      # provisional: 04 addrHi addrLo len
    WRITE_RAM = 0x05     # provisional: 05 addrHi addrLo len data...
    IDENTIFY = 0x08
    SET_BAUD = 0x0A


class BaudCode(IntEnum):
    HIGH = 0x03      # host then reopens at 230400 (or 250000, see HIGH_WOQ_HOST_BAUD)
    LOW = 0x2F
    LOW_WOQ = 0x33


LOW_HOST_BAUD = 19200
HIGH_HOST_BAUD = 230400
HIGH_WOQ_HOST_BAUD = 250000

# Commands that change device state. The client refuses these unless writes are enabled.
MUTATING = frozenset({Cmd.WRITE_RAM, 0x02, 0x03, 0x07, 0x11, 0x34, 0x35, 0x36, 0x37})


def _addr(address: int) -> bytes:
    if not 0 <= address <= 0xFFFF:
        raise ValueError(f"address 0x{address:x} out of 16-bit range")
    return address.to_bytes(2, "big")


def identify() -> bytes:
    return bytes([Cmd.IDENTIFY])


def set_baud(code: BaudCode) -> bytes:
    return bytes([Cmd.SET_BAUD, code])


def read_ram(address: int, length: int) -> bytes:
    if not 0 < length < 0x100:
        raise ValueError("length must be 1..255")
    return bytes([Cmd.READ_RAM]) + _addr(address) + bytes([length])


def write_ram(address: int, data: bytes) -> bytes:
    if not 0 < len(data) < 0xFA:
        raise ValueError("data length must be 1..249")
    return bytes([Cmd.WRITE_RAM]) + _addr(address) + bytes([len(data)]) + data


@dataclass(frozen=True)
class DeviceInfo:
    raw: bytes
    model_string: str | None
    model_type: int | None
    program_loaded: bool | None


# Prefix table from FUN_0051d790 (first match wins, order matters).
MODEL_PREFIXES: list[tuple[str, int, str]] = [
    ("DSPULTRA", 0x16, "HELIX DSP ULTRA"),
    ("DSP-PRO", 0x06, "HELIX DSP PRO"),
    ("DSPMINIMK2", 0x1F, "HELIX DSP MINI MK2"),
    ("DSP2", 0x0E, "HELIX DSP.2"),
    ("DSP3S", 0x21, "HELIX DSP.3S"),
    ("DSP3", 0x15, "HELIX DSP.3"),
    ("2DSP-PRO", 0x0F, "HELIX DSP PRO MK2"),
    ("BRAX-DSP", 0x11, "BRAX DSP"),
    ("HELI", 0x02, "HELIX DSP"),
]
PRO_MK2 = 0x0F


def parse_identify(payload: bytes) -> DeviceInfo:
    """Best-effort parse. The exact offset of the model string inside the
    179-byte payload is not yet known, so search for any known prefix."""
    text = payload.decode("latin-1")
    best: tuple[int, str, int] | None = None
    for prefix, mtype, _ in MODEL_PREFIXES:
        i = text.find(prefix)
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(prefix) > len(best[1]))):
            best = (i, prefix, mtype)
    if best is None:
        return DeviceInfo(payload, None, None, None)
    i = best[0]
    end = i
    while end < len(text) and 0x20 <= ord(text[end]) < 0x7F:
        end += 1
    return DeviceInfo(payload, text[i:end].strip(), best[2], None)
