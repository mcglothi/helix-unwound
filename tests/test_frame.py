import pytest

from helixtune.protocol import frame


def test_probe_frame_matches_decompiled_layout():
    # cmd 08 identify, 1-byte payload, channel 1 (FUN_0075db80 -> FUN_0056c710)
    assert frame.encode_tx(b"\x08") == bytes([0x42, 0x02, 0xFD, 0x01, 0x08, 0x08])


def test_tx_roundtrip():
    payload = bytes([0x05, 0x18, 0x24, 0x04, 0x01, 0x00, 0x00, 0x00])
    f, used = frame.decode_tx(frame.encode_tx(payload))
    assert f.payload == payload and f.channel == 1 and used == len(payload) + 5


def test_rx_roundtrip_and_checksum_wraps():
    payload = bytes([0xFF] * 10)
    raw = frame.encode_rx(payload)
    assert raw[-1] == (0xFF * 10) & 0xFF
    f, _ = frame.decode_rx(raw)
    assert f.payload == payload


@pytest.mark.parametrize("corrupt", [0, 2, -1])
def test_rx_rejects_corruption(corrupt):
    raw = bytearray(frame.encode_rx(b"\x01\x02\x03"))
    raw[corrupt] ^= 0x01
    with pytest.raises(frame.FrameError):
        frame.decode_rx(bytes(raw))
