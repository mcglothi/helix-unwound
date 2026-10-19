"""Emulator behaviour pinned to the 2026-10-17 USB captures (synthetic contents only)."""
import struct
import zlib

import pytest

from helixtune import stored_preset
from helixtune.emulator import EmulatedDevice
from helixtune.protocol import commands, frame
from helixtune.protocol.client import Client
from helixtune.protocol.session import wire_commands


def send(dev, payload):
    dev.write(frame.encode_tx(payload))
    raw = dev.read(4096)
    return frame.decode_rx(raw)[0] if raw else None


def test_identify_uses_the_captured_layout():
    dev = EmulatedDevice()
    p = dev.identify_payload
    assert len(p) == 174 and p[0] == 0x08 and p[6:10] == b"R1R1" and p[142:150] == b"2DSP-PRO"
    info = Client(dev).identify()
    assert info.model_type == commands.PRO_MK2


def test_keepalive_echoes_and_session_is_silent():
    dev = EmulatedDevice()
    ping = bytes.fromhex("02 00 22 b8 00 00 00 00")
    assert send(dev, ping).payload == ping
    assert send(dev, bytes([0x09, 0x01])) is None and dev.session_open
    assert send(dev, bytes([0x09, 0x00])) is None and not dev.session_open
    assert send(dev, bytes.fromhex("1b 06 00 00 00 00 00 00")).payload == bytes.fromhex("1b 06 00 00 00 00 02 02")


def _blob(xml: bytes) -> bytes:
    return struct.pack(">I", len(xml)) + zlib.compress(xml)


def _backup(dev):
    client = Client(dev, timeout=0.05)
    return stored_preset.backup(client, lambda b: setattr(dev, "baudrate", b), sleep=lambda s: None)


def test_stored_preset_backup_round_trips_through_the_emulator():
    xml = b'<ATF Dev="15" V="4.80b"><OC ON="0" CN="7" LG="2"/></ATF>'
    dev = EmulatedDevice(stored_name=b"JTest preset", stored_blob=_blob(xml))
    preset = _backup(dev)
    assert preset.xml == xml and preset.name_bytes.startswith(b"JTest preset")
    sent = wire_commands(b"".join(dev.log))
    first_read = next(i for i, p in enumerate(sent) if p[:2] == b"\x32\x03")
    assert sent[first_read - 1] == commands.SELECT_STORED              # selection before any read
    assert all(commands.is_safe_read(p) or p == b"SYNC" or commands.is_backup_session_command(p) for p in sent)
    assert sent[first_read][:5] == bytes.fromhex("32 03 00 00 12") and sent[first_read + 1][:5] == bytes.fromhex("32 03 00 12 80")
    assert sent[-3:] == [commands.SESSION_END, commands.set_baud(commands.BaudCode.LOW), b"SYNC"]
    assert not dev.session_open and dev.device_baud == commands.LOW_HOST_BAUD


def test_stored_reads_are_silent_until_selected_and_selection_persists():
    """2026-10-18 hardware: 32 03 timed out until 32 01 06 00; afterwards it answered even at
    19200 without a session."""
    dev = EmulatedDevice(stored_name=b"JTest", stored_blob=_blob(b'<ATF Dev="15"/>'))
    with pytest.raises(TimeoutError):
        Client(dev, timeout=0.05).read_stored(0, 18)
    _backup(dev)
    assert dev.stored_selected and Client(dev, timeout=0.05).read_stored(0, 18).startswith(b"JTest")


def test_empty_emulator_flash_is_rejected_not_imported():
    dev = EmulatedDevice()
    with pytest.raises(stored_preset.StoredPresetError):
        _backup(dev)
    assert not dev.session_open and dev.device_baud == commands.LOW_HOST_BAUD   # closed on failure
