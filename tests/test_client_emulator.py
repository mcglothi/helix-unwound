import pytest

from helixtune.emulator import EmulatedDevice
from helixtune.protocol import commands
from helixtune.protocol.client import Client, WritesDisabled


def test_identify_detects_pro_mk2():
    info = Client(EmulatedDevice()).identify()
    assert info.model_type == commands.PRO_MK2
    assert info.model_string.startswith("2DSP-PRO")


def test_identify_prefers_longest_prefix_at_same_offset():
    payload = b"\x00" * 10 + b"DSP3S" + b"\x00" * 10
    assert commands.parse_identify(payload).model_type == 0x21


def test_writes_refused_by_default():
    dev = EmulatedDevice()
    with pytest.raises(WritesDisabled):
        Client(dev).write_ram(0x1824, b"\x01\x00\x00\x00")
    assert dev.log == []  # nothing reached the device


def test_write_and_inspect_emulator_memory_when_enabled():
    dev = EmulatedDevice()
    c = Client(dev, allow_writes=True)
    ack = c.write_ram(0x1824, b"\x01\x02\x03\x04")
    assert len(ack.payload) == 5
    assert ack.payload == bytes.fromhex("03 00 01 18 24")
    assert dev.ram[0x1824 * 4:0x1824 * 4 + 4] == b"\x01\x02\x03\x04"
