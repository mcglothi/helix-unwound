"""Request/response client over any byte transport (real serial port or emulator)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, Protocol

from . import commands, frame


class Transport(Protocol):
    def write(self, data: bytes) -> int: ...
    def read(self, size: int) -> bytes: ...
    def reset_input_buffer(self) -> None: ...


class WritesDisabled(PermissionError):
    pass


# drain() and _read_frame() enforce their deadlines between reads; one blocking read must not
# outlast them, so physical ports need a short read timeout (the CLI/API open at 0.05 s).
MAX_PORT_READ_TIMEOUT_S = 0.1


class Client:
    def __init__(self, transport: Transport, *, allow_writes: bool = False, timeout: float = 0.5):
        self.t = transport
        self.allow_writes = allow_writes
        self.timeout = timeout
        self._backup_mode = False
        port_timeout = getattr(transport, "timeout", 0)
        if self._physical() and hasattr(transport, "timeout") and (
                port_timeout is None or port_timeout > MAX_PORT_READ_TIMEOUT_S):
            raise ValueError(f"serial read timeout must be set and at most {MAX_PORT_READ_TIMEOUT_S} s "
                             f"(got {port_timeout!r}); a blocking read could outlast the protocol deadlines")

    @contextmanager
    def stored_backup_mode(self) -> Iterator[None]:
        """Let a physical transport carry the session commands a stored-preset backup needs
        (session start/end, baud switch, sync, keep-alive, 32 01 06 00). Never parameter writes."""
        self._backup_mode = True
        try:
            yield
        finally:
            self._backup_mode = False

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

    def _physical(self) -> bool:
        from ..emulator import EmulatedDevice
        return not isinstance(self.t, EmulatedDevice)

    def _gate(self, payload: bytes) -> None:
        if not payload:
            raise ValueError("empty command")
        if self._physical() and not (commands.is_safe_read(payload)
                                     or (self._backup_mode and commands.is_backup_session_command(payload))):
            raise WritesDisabled("Physical transports permit only identify and bounded stored-preset reads (plus the backup session); all other commands remain disabled")
        if payload[0] in (0x04, 0x05):
            raise WritesDisabled("Commands 04/05 are preset-storage operations, not RAM access; unsupported")
        if payload[0] in commands.MUTATING and not self.allow_writes:
            raise WritesDisabled(f"command 0x{payload[0]:02x} mutates the device; writes are disabled")

    def transact(self, payload: bytes, *, timeout: float | None = None) -> frame.Frame:
        self._gate(payload)
        self.t.reset_input_buffer()
        self.t.write(frame.encode_tx(payload))
        return self._read_frame(timeout or self.timeout)

    def send(self, payload: bytes) -> None:
        """Fire-and-forget (session start/end, baud change): no reply or a truncated one."""
        self._gate(payload)
        self.t.reset_input_buffer()
        self.t.write(frame.encode_tx(payload))

    def send_sync(self) -> None:
        """The 10 x 42 00 burst PC-Tool sends around every baud change."""
        if self._physical() and not self._backup_mode:
            raise WritesDisabled("Physical transports permit only identify and bounded stored-preset reads; all other commands remain disabled")
        self.t.write(frame.SYNC_FRAME)

    DRAIN_MAX_BYTES = 4096
    DRAIN_DEADLINE_S = 0.25

    def drain(self) -> bytes:
        """Discard whatever arrived (e.g. a baud ack truncated by the rate change).
        Bounded by bytes and time so a chattering line cannot stall the caller."""
        got = bytearray()
        deadline = time.monotonic() + self.DRAIN_DEADLINE_S
        while len(got) < self.DRAIN_MAX_BYTES and time.monotonic() < deadline:
            chunk = self.t.read(256)
            if not chunk:
                break
            got += chunk
        self.t.reset_input_buffer()
        return bytes(got)

    def identify(self) -> commands.DeviceInfo:
        return commands.parse_identify(self.transact(commands.identify()).payload)

    def read_ram(self, address: int, length: int) -> bytes:
        return self.transact(commands.read_ram(address, length)).payload

    def read_stored(self, address: int, length: int) -> bytes:
        request = commands.read_stored(address, length)
        reply = self.transact(request)
        name = address == 0 and length == 18
        expected_length = 5 + length + (0 if name else 1)
        if (reply.channel != frame.DEFAULT_CHANNEL or len(reply.payload) != expected_length
                or reply.payload[:5] != request[:5] or (not name and reply.payload[-1] != 0)):
            raise frame.FrameError("stored-preset reply does not match command, address and requested length")
        return reply.payload[5:5 + length]

    def write_ram(self, address: int, data: bytes) -> frame.Frame:
        payload = commands.write_ram(address, data)
        reply = self.transact(payload)
        if reply.channel != frame.DEFAULT_CHANNEL or reply.payload != payload[:5]:
            raise frame.FrameError("parameter-write acknowledgement does not match command, bank and address")
        return reply
