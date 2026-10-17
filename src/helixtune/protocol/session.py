"""PC-Tool session handling, replayed from the 2026-10-17 USB captures.

Open (capture 01b-connect-click):
  1. baud recovery at 19200: 0A 03, sync, host -> high; 0A 2F, sync, host -> 19200
     (returns a DSP left at high speed by an earlier session to 19200)
  2. identify (must be a PRO MK2)
  3. 09 01 (session start, no reply)
  4. 0A 03, sync, wait ~0.5 s, host -> high, sync
Idle: keep-alive 02 00 22 b8 00 00 00 00, echoed unchanged.
Close (capture 17-disconnect): 09 00, 0A 2F, sync, wait ~0.5 s, host -> 19200.

Baud-change acknowledgements arrive truncated while the line rate changes; they are
drained, not validated. Physical transports remain gated by Client: this module is
exercised against the emulator until a supervised live test.
"""
from __future__ import annotations

import time
from typing import Callable

from . import commands, frame
from .client import Client

KEEPALIVE = bytes.fromhex("02 00 22 b8 00 00 00 00")
SESSION_START = bytes([0x09, 0x01])
SESSION_END = bytes([0x09, 0x00])
BAUD_HIGH = commands.set_baud(commands.BaudCode.HIGH)
BAUD_LOW = commands.set_baud(commands.BaudCode.LOW)
SETTLE_S = 0.5       # PC-Tool waits ~500 ms between the sync burst and the host baud switch
ACK_WAIT_S = 0.05


class SessionError(RuntimeError):
    pass


class Session:
    def __init__(self, client: Client, set_host_baud: Callable[[int], None], *,
                 high_baud: int = commands.HIGH_HOST_BAUD, sleep: Callable[[float], None] = time.sleep):
        self.client = client
        self.set_host_baud = set_host_baud
        self.high_baud = high_baud
        self.sleep = sleep
        self.open_ = False
        self.info: commands.DeviceInfo | None = None

    # -- low-level steps -----------------------------------------------------------------
    def _switch(self, code_payload: bytes, host_baud: int) -> None:
        self.client.send(code_payload)
        self.sleep(ACK_WAIT_S)
        self.client.drain()                 # truncated ack at the rate change
        self.client.send_sync()
        self.sleep(SETTLE_S)
        self.set_host_baud(host_baud)

    # -- public --------------------------------------------------------------------------
    def open(self) -> commands.DeviceInfo:
        if self.open_:
            raise SessionError("session already open")
        self.set_host_baud(commands.LOW_HOST_BAUD)
        self._switch(BAUD_HIGH, self.high_baud)      # recovery dance
        self._switch(BAUD_LOW, commands.LOW_HOST_BAUD)
        info = self.client.identify()
        if info.model_type != commands.PRO_MK2:
            raise SessionError(f"connected device is {info.model_string!r}, not a HELIX DSP PRO MK2")
        self.client.send(SESSION_START)
        self.sleep(ACK_WAIT_S)
        self.client.drain()
        self._switch(BAUD_HIGH, self.high_baud)
        self.client.send_sync()
        self.keepalive()                              # proves the high-speed link answers
        self.open_, self.info = True, info
        return info

    def keepalive(self) -> None:
        reply = self.client.transact(KEEPALIVE)
        if reply.payload != KEEPALIVE:
            raise SessionError(f"keep-alive not echoed (got {reply.payload.hex(' ')})")

    def close(self) -> None:
        """Always tries to leave the DSP and host at 19200, even after errors."""
        try:
            self.client.send(SESSION_END)
            self.sleep(ACK_WAIT_S)
            self.client.drain()
            self._switch(BAUD_LOW, commands.LOW_HOST_BAUD)
        finally:
            self.open_ = False

    def __enter__(self) -> "Session":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def wire_commands(raw_tx: bytes) -> list[bytes]:
    """Split a host->device byte stream into frames and sync bursts (for tests/diffs)."""
    out, i = [], 0
    while i < len(raw_tx):
        if raw_tx[i:i + len(frame.SYNC_FRAME)] == frame.SYNC_FRAME:
            out.append(b"SYNC")
            i += len(frame.SYNC_FRAME)
            continue
        f, n = frame.decode_tx(raw_tx[i:])
        out.append(f.payload)
        i += n
    return out
