"""In-memory stand-in for a HELIX DSP PRO MK2, speaking the decoded protocol.

Behaviour follows the 2026-10-17 USB captures: identify layout, parameter write echo,
keep-alive echo, status poll, silent session start/end and stored-preset reads.
Field contents (unit code, RAM, stored preset) are synthetic unless supplied;
emulator success is not evidence of successful hardware tuning.
"""

from __future__ import annotations

from .protocol import commands, frame


def default_identify_payload() -> bytes:
    """Captured layout (offsets within the 174-byte reply payload, which starts with the
    08 command byte): header @1, program version "R1R1" @6, copyright @14, unit code @78
    (zeros here; the real one is unit-specific), model string "2DSP-PRO" @142."""
    body = bytearray(commands.IDENTIFY_RESPONSE_LEN)
    body[0] = commands.Cmd.IDENTIFY
    body[1:6] = bytes.fromhex("3ee63ee601")
    body[6:10] = b"R1R1"
    text = b"Audiotec Fischer (c)2016 1.0"
    body[14:14 + len(text)] = text
    body[142:150] = b"2DSP-PRO"
    body[158] = 0xA0
    return bytes(body)


KEEPALIVE = 0x02
SESSION = 0x09
STATUS = 0x1B
STORED = 0x32
STORED_NAME_LEN = 18


class EmulatedDevice:
    """Implements the Transport protocol directly (write = host->device bytes)."""

    def __init__(self, identify_payload: bytes | None = None, ram_words: int = 0x10000,
                 stored_name: bytes = b"", stored_blob: bytes = b""):
        self.identify_payload = identify_payload or default_identify_payload()
        # Stored-preset memory as read by 32 03: 18-byte name, then the qCompress blob.
        # Unwritten flash reads back as 0xFF.
        self.stored = bytearray(b"\xff" * 0x10000)
        name = stored_name[:STORED_NAME_LEN].ljust(STORED_NAME_LEN, b" ")
        self.stored[:STORED_NAME_LEN] = name
        self.stored[STORED_NAME_LEN:STORED_NAME_LEN + len(stored_blob)] = stored_blob
        self.session_open = False
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
        reply = self._handle(req.payload)
        if reply is not None:  # session start/end is not answered on the wire
            self._out += frame.encode_rx(reply, channel=req.channel)
        return len(data)

    def read(self, size: int) -> bytes:
        out, self._out = bytes(self._out[:size]), self._out[size:]
        return out

    # Command handling
    def _handle(self, p: bytes) -> bytes | None:
        cmd = p[0]
        if cmd == KEEPALIVE:
            return p  # echoed unchanged
        if cmd == SESSION and len(p) == 2:
            self.session_open = p[1] == 1
            return None
        if cmd == STATUS:
            return bytes([STATUS, 0x06, 0, 0, 0, 0, 0x02, 0x02])
        if cmd == STORED and len(p) >= 5 and p[1] == 0x03:
            addr, n = int.from_bytes(p[2:4], "big"), p[4]
            if addr + n > len(self.stored):
                return bytes([cmd, 0xFF])
            trailer = b"" if (addr == 0 and n == STORED_NAME_LEN) else b"\x00"
            return p[:5] + bytes(self.stored[addr:addr + n]) + trailer
        if cmd == commands.Cmd.IDENTIFY:
            return self.identify_payload
        if cmd == commands.Cmd.SET_BAUD:
            self.baud_code = p[1]
            return bytes([cmd])
        if cmd == commands.Cmd.WRITE_RAM:
            if len(p) < 9 or p[1:3] != b"\x00\x01" or (len(p) - 5) % 4:
                return bytes([cmd, 0xFF])
            addr, data = int.from_bytes(p[3:5], "big"), p[5:]
            self.ram[addr * 4 : addr * 4 + len(data)] = data
            return p[:5]
        return bytes([cmd, 0xFF])
