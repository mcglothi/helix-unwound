"""Request/response client over any byte transport (real serial port or emulator)."""

from __future__ import annotations

import time
from typing import Protocol

from . import commands, frame


class Transport(Protocol):
    def write(self, data: bytes) -> int: ...
    def read(self, size: int) -> bytes: ...
    def reset_input_buffer(self) -> None: ...


class WritesDisabled(PermissionError):
    pass


class Client:
    def __init__(self, transport: Transport, *, allow_writes: bool = False, timeout: float = 0.5):
        self.t = transport
        self.allow_writes = allow_writes
        self.timeout = timeout

    def _read_frame(self, timeout: float) -> frame.Frame:
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.t.read(256)
            if chunk:
                buf += chunk
                # resync to start byte
                start = buf.find(bytes([frame.RX_START]))
                if start > 0:
                    del buf[:start]
                if len(buf) >= 5 and len(buf) >= 4 + buf[1] + 1:
                    f, _ = frame.decode_rx(bytes(buf))
                    return f
        raise TimeoutError(f"no complete reply frame (got {bytes(buf).hex(' ')})")

    def transact(self, payload: bytes, *, timeout: float | None = None) -> frame.Frame:
        if not payload:
            raise ValueError("empty command")
        from ..emulator import EmulatedDevice
        if not isinstance(self.t, EmulatedDevice) and payload != commands.identify():
            raise WritesDisabled("Physical transports are identify-only until captured session and parameter rendering are validated; emulator writes remain available")
        if payload[0] in (0x04, 0x05):
            raise WritesDisabled("Commands 04/05 are preset-storage operations, not RAM access; unsupported")
        if payload[0] in commands.MUTATING and not self.allow_writes:
            raise WritesDisabled(f"command 0x{payload[0]:02x} mutates the device; writes are disabled")
        self.t.reset_input_buffer()
        self.t.write(frame.encode_tx(payload))
        return self._read_frame(timeout or self.timeout)

    def identify(self) -> commands.DeviceInfo:
        return commands.parse_identify(self.transact(commands.identify()).payload)

    def read_ram(self, address: int, length: int) -> bytes:
        return self.transact(commands.read_ram(address, length)).payload

    def write_ram(self, address: int, data: bytes) -> frame.Frame:
        payload = commands.write_ram(address, data)
        reply = self.transact(payload)
        if reply.channel != frame.DEFAULT_CHANNEL or reply.payload != payload[:5]:
            raise frame.FrameError("parameter-write acknowledgement does not match command, bank and address")
        return reply
