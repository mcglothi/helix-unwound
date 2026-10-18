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


def _rate(baud: int) -> str:
    # FT232R runs 230400 as 230769; both are "high".
    return "high" if baud >= 200000 else "low"


# Truncated acknowledgements exactly as captured (01b-connect-click).
BAUD_ACKS = {commands.BaudCode.HIGH: bytes.fromhex("43 02 fd 01 0a ff"),
             commands.BaudCode.LOW: bytes.fromhex("43 02 fd 01 0a fe 00 00 00 00 00")}

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
        # 2026-10-18 hardware: 32 03 is silent until 32 01 06 00; the selection then persists.
        self.stored_selected = False
        self.keepalive_tail = 0        # set nonzero to model a DSP playing audio
        # Line rate: the DSP and the host must agree, or bytes arrive as garbage.
        self.device_baud = commands.LOW_HOST_BAUD
        self.baudrate = commands.LOW_HOST_BAUD    # host side, set by the session layer
        self.garbled = 0
        self.ram = bytearray(ram_words * 4)  # 32-bit SigmaDSP words, byte-addressed by word*4
        self.baud_code: int | None = None
        self._out = bytearray()
        self.log: list[bytes] = []

    # Transport interface
    def reset_input_buffer(self) -> None:
        self._out.clear()

    def write(self, data: bytes) -> int:
        self.log.append(bytes(data))
        if bytes(data) == frame.SYNC_FRAME:
            return len(data)           # resync burst; sent at either rate around a switch
        if _rate(self.baudrate) != _rate(self.device_baud):
            self.garbled += 1          # wrong line rate: the DSP sees noise and stays silent
            return len(data)
        req, _ = frame.decode_tx(bytes(data))
        if req.payload[:1] == bytes([commands.Cmd.SET_BAUD]) and len(req.payload) == 2:
            # Captured acks are truncated by the rate change; then the DSP switches.
            self._out += BAUD_ACKS.get(req.payload[1], b"")
            self.baud_code = req.payload[1]
            self.device_baud = (commands.HIGH_HOST_BAUD if req.payload[1] == commands.BaudCode.HIGH
                                else commands.LOW_HOST_BAUD)
            return len(data)
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
            # echoed; the last byte is a live value on hardware (nonzero while audio plays)
            return p[:-1] + bytes([self.keepalive_tail]) if len(p) == 8 else p
        if cmd == SESSION and len(p) == 2:
            self.session_open = p[1] == 1
            return None
        if cmd == STATUS:
            return bytes([STATUS, 0x06, 0, 0, 0, 0, 0x02, 0x02])
        if p == commands.SELECT_STORED:
            self.stored_selected = True
            return p                   # echoed
        if cmd == STORED and p[1:2] == b"\x0f":
            return p                   # captured echo; meaning unknown
        if cmd == STORED and len(p) >= 5 and p[1] == 0x03:
            if not self.stored_selected:
                return None            # no reply before the selection

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
