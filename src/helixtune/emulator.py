"""In-memory stand-in for a HELIX DSP PRO MK2, speaking the decoded protocol.

Behaviour beyond identify is modelled on our current (unverified) reading of the
command table; replace guesses with captured responses as they arrive.
"""

from __future__ import annotations

from .protocol import commands, frame


def default_identify_payload() -> bytes:
    # Placeholder layout: real offsets unknown. Model string lives somewhere in 179 bytes.
    body = bytearray(commands.IDENTIFY_RESPONSE_LEN)
    model = b"2DSP-PRO MK2"
    body[0x18] = ord("R")
    body[0x60 : 0x60 + len(model)] = model
    return bytes(body)


class EmulatedDevice:
    """Implements the Transport protocol directly (write = host->device bytes)."""

    def __init__(self, identify_payload: bytes | None = None, ram_words: int = 0x10000):
        self.identify_payload = identify_payload or default_identify_payload()
        self.ram = bytearray(ram_words * 4)  # 32-bit SigmaDSP words, byte-addressed by word*4
        self.baud_code: int | None = None
        self._out = bytearray()
        self.log: list[bytes] = []

    # Transport interface
    def reset_input_buffer(self) -> None:
        self._out.clear()

    def write(self, data: bytes) -> int:
        self.log.append(bytes(data))
        req, _ = frame.decode_tx(bytes(data))
        self._out += frame.encode_rx(self._handle(req.payload), channel=req.channel)
        return len(data)

    def read(self, size: int) -> bytes:
        out, self._out = bytes(self._out[:size]), self._out[size:]
        return out

    # Command handling
    def _handle(self, p: bytes) -> bytes:
        cmd = p[0]
        if cmd == commands.Cmd.IDENTIFY:
            return self.identify_payload
        if cmd == commands.Cmd.SET_BAUD:
            self.baud_code = p[1]
            return bytes([cmd])
        if cmd == commands.Cmd.READ_RAM:
            addr, n = int.from_bytes(p[1:3], "big"), p[3]
            return bytes(self.ram[addr * 4 : addr * 4 + n])
        if cmd == commands.Cmd.WRITE_RAM:
            addr, n = int.from_bytes(p[1:3], "big"), p[3]
            self.ram[addr * 4 : addr * 4 + n] = p[4 : 4 + n]
            return bytes([cmd, 0, 0, 0, 0])  # 5-byte payload -> 10-byte ack frame
        return bytes([cmd, 0xFF])
