"""Serial framing for the HELIX DSP PC-Tool protocol.

Derived statically from ATF_DSP_PC-TOOL.exe 4.80b (see notes/FINDINGS.md):
  TX serializer  FUN_0056c710
  RX validator   FUN_0056c810

TX N+1, RX N and sum8 framing matched the 2026-10-17 PC-Tool USB captures.
This does not validate every command or its parameter semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

TX_START = 0x42  # 'B' host -> device
RX_START = 0x43  # 'C' device -> host
DEFAULT_CHANNEL = 0x01

# Sent instead of a normal frame when the uartbuffer "sync" flag is set.
SYNC_FRAME = bytes([0x42, 0x00] * 10)


class FrameError(ValueError):
    pass


def checksum(payload: bytes) -> int:
    return sum(payload) & 0xFF


def encode_tx(payload: bytes, channel: int = DEFAULT_CHANNEL) -> bytes:
    n = len(payload)
    if not 0 < n < 0xFF:
        raise FrameError(f"payload length {n} out of range")
    length = (n + 1) & 0xFF
    return bytes([TX_START, length, length ^ 0xFF, channel & 0xFF]) + payload + bytes([checksum(payload)])


def encode_rx(payload: bytes, channel: int = DEFAULT_CHANNEL) -> bytes:
    """Build a device->host frame (used by the emulator)."""
    n = len(payload)
    if not 0 <= n <= 0xFF:
        raise FrameError(f"payload length {n} out of range")
    return bytes([RX_START, n, n ^ 0xFF, channel & 0xFF]) + payload + bytes([checksum(payload)])


@dataclass(frozen=True)
class Frame:
    start: int
    channel: int
    payload: bytes


def _decode(buf: bytes, start: int, length_bias: int) -> tuple[Frame, int]:
    """Decode one frame from the front of buf. Returns (frame, bytes_consumed)."""
    if len(buf) < 5:
        raise FrameError("short frame")
    if buf[0] != start:
        raise FrameError(f"bad start byte 0x{buf[0]:02x}")
    if buf[1] != buf[2] ^ 0xFF:
        raise FrameError("length/inverse mismatch")
    n = buf[1] - length_bias
    if n < 0:
        raise FrameError("negative payload length")
    total = 4 + n + 1
    if len(buf) < total:
        raise FrameError("truncated frame")
    payload = bytes(buf[4 : 4 + n])
    if buf[4 + n] != checksum(payload):
        raise FrameError("checksum mismatch")
    return Frame(start=buf[0], channel=buf[3], payload=payload), total


def decode_rx(buf: bytes) -> tuple[Frame, int]:
    return _decode(buf, RX_START, 0)


def decode_tx(buf: bytes) -> tuple[Frame, int]:
    return _decode(buf, TX_START, 1)
