"""Command payload builders (inner payload, before framing).

Parameter-write layout follows the 2026-10-17 PC-Tool USB captures: command
03, bank 0001, 16-bit big-endian word address, whole 32-bit words. Preset-storage
commands 04/05 must never be treated as RAM access. Other command families and
full hardware session integration remain incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

IDENTIFY_RESPONSE_LEN = 174  # captured payload; 179 bytes including frame overhead
WRITE_ACK_FRAME_LEN = 10     # captured parameter echo: 5-byte payload + frame overhead


class Cmd(IntEnum):
    WRITE_RAM = 0x03     # captured: 03 00 01 addr16 + 32-bit words; no inner length
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
MUTATING = frozenset({Cmd.WRITE_RAM, 0x04, 0x05, 0x07, 0x11, 0x34, 0x35, 0x36, 0x37})


def _addr(address: int) -> bytes:
    if not 0 <= address <= 0xFFFF:
        raise ValueError(f"address 0x{address:x} out of 16-bit range")
    return address.to_bytes(2, "big")


def identify() -> bytes:
    return bytes([Cmd.IDENTIFY])


def set_baud(code: BaudCode) -> bytes:
    return bytes([Cmd.SET_BAUD, code])


def read_ram(address: int, length: int) -> bytes:
    raise NotImplementedError("RAM readback is not established; commands 04/05 operate on preset storage")


def write_ram(address: int, data: bytes) -> bytes:
    if not data or len(data) % 4 or len(data) > 248:
        raise ValueError("parameter data must contain 1..62 complete 32-bit words")
    if address + len(data) // 4 > 0x10000:
        raise ValueError("parameter write exceeds 16-bit address space")
    return bytes([Cmd.WRITE_RAM, 0, 1]) + _addr(address) + data


def read_stored(address: int, length: int) -> bytes:
    if not isinstance(address, int) or not 0 <= address < 0x10000:
        raise ValueError("stored-preset address out of range")
    if not isinstance(length, int) or not 1 <= length <= 128 or address + length > 0x10000:
        raise ValueError("stored-preset read must contain 1..128 bytes within memory bounds")
    name = address == 0 and length == 18
    if address < 18 and not name:
        raise ValueError("stored-preset name must be read as one 18-byte block")
    # Captured requests include a receive-sized body, sometimes containing stale
    # PC-Tool buffer bytes. Match the size, but never send arbitrary buffer data.
    padding = length if name else length + 1
    return bytes([0x32, 0x03, address >> 8, address & 0xff, length]) + bytes(padding)


# PC-Tool session commands (2026-10-17 captures).
SESSION_START = bytes([0x09, 0x01])
SESSION_END = bytes([0x09, 0x00])
KEEPALIVE = bytes.fromhex("02 00 22 b8 00 00 00 00")
# 2026-10-18 live test: stored reads (32 03) get no reply until 32 01 06 00 has been sent and
# echoed; the selection then persisted across sessions. PC-Tool sends it before its first
# stored read. The meaning of 06 is not decoded, so only this exact payload is ever sent.
SELECT_STORED = bytes.fromhex("32 01 06 00")


def is_backup_session_command(payload: bytes) -> bool:
    """The commands a stored-preset backup may add to identify and bounded 32 03 reads."""
    return payload in (SESSION_START, SESSION_END, KEEPALIVE, SELECT_STORED,
                       set_baud(BaudCode.HIGH), set_baud(BaudCode.LOW))


def is_safe_read(payload: bytes) -> bool:
    if payload == identify():
        return True
    if len(payload) >= 5 and payload[:2] == b"\x32\x03":
        try:
            return payload == read_stored(int.from_bytes(payload[2:4], "big"), payload[4])
        except ValueError:
            pass
    return False


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
    174-byte payload is not yet known, so search for any known prefix."""
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
