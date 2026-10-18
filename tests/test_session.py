"""Session layer replaying PC-Tool's captured open/keep-alive/close sequence (emulator only)."""
from pathlib import Path

import pytest

from helixtune.emulator import EmulatedDevice
from helixtune.protocol import commands
from helixtune.protocol.client import Client, WritesDisabled
from helixtune.protocol.session import Session, SessionError, wire_commands

LOW, HIGH = commands.LOW_HOST_BAUD, commands.HIGH_HOST_BAUD
H = bytes.fromhex


def make(dev=None, **kw):
    dev = dev or EmulatedDevice()
    bauds = []

    def set_baud(b):
        bauds.append(b)
        dev.baudrate = b
    return dev, bauds, Session(Client(dev, allow_writes=True, timeout=0.05), set_baud, sleep=lambda s: None, **kw)


def wait_for(cond, timeout=3.0, step=0.01):
    """Poll instead of fixed sleeps: CI runners (macOS) schedule threads slowly."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(step)
    return cond()


def sent(dev):
    return wire_commands(b"".join(dev.log))


def test_open_keepalive_close_matches_pc_tool_wire_order():
    dev, bauds, s = make()
    s.open()
    s.keepalive()
    s.close()
    assert sent(dev) == [
        H("0a 03"), b"SYNC", H("0a 2f"), b"SYNC",            # recovery dance (captured 0.60-1.65 s)
        H("08"), H("09 01"),                                   # identify, session start
        H("0a 03"), b"SYNC", b"SYNC",                          # to high: sync before and after the switch
        H("02 00 22 b8 00 00 00 00"), H("02 00 22 b8 00 00 00 00"),
        H("09 00"), H("0a 2f"), b"SYNC",                       # close (captured 17-disconnect)
    ]
    assert bauds == [LOW, HIGH, LOW, HIGH, LOW]
    assert dev.device_baud == LOW and not dev.session_open and dev.garbled == 0


def test_writes_inside_a_session_run_at_high_speed():
    dev, _, s = make()
    with s:
        assert dev.device_baud == HIGH and dev.session_open
        s.client.write_ram(0x215C, H("00 00 00 dc"))
    assert dev.ram[0x215C * 4:0x215C * 4 + 4] == H("00 00 00 dc")


def test_recovers_a_dsp_left_at_high_speed():
    dev = EmulatedDevice()
    dev.device_baud = HIGH                  # previous session ended without lowering the rate
    dev, _, s = make(dev)
    s.open()
    assert dev.garbled >= 1 and s.open_    # first 0A 03 at 19200 was noise; 0A 2F at high recovered it
    s.close()
    assert dev.device_baud == LOW


def test_a_missing_host_baud_switch_is_detected_not_ignored():
    dev = EmulatedDevice()
    s = Session(Client(dev, allow_writes=True, timeout=0.05), lambda b: None, sleep=lambda x: None)
    with pytest.raises((TimeoutError, SessionError)):
        s.open()                            # DSP goes high, host stays low: keep-alive must fail


def test_non_pro_mk2_is_refused_before_session_start():
    payload = bytearray(EmulatedDevice().identify_payload)
    payload[142:150] = b"OTHERDEV"
    dev, _, s = make(EmulatedDevice(identify_payload=bytes(payload)))
    with pytest.raises(SessionError, match="not a HELIX DSP PRO MK2"):
        s.open()
    assert H("09 01") not in sent(dev)


class Recording:
    def __init__(self): self.log = []
    def reset_input_buffer(self): pass
    def write(self, data): self.log.append(data); return len(data)
    def read(self, size): return b""


def test_physical_transports_never_receive_session_bytes():
    t = Recording()
    s = Session(Client(t, allow_writes=True), lambda b: None, sleep=lambda x: None)
    with pytest.raises(WritesDisabled):
        s.open()
    assert t.log == []


def test_private_capture_open_sequence_if_available():
    """Compare against the real PC-Tool capture when the private pcap is present."""
    root = Path(__file__).resolve().parents[1]
    pcap = root / "captures/usb/01b-connect-click.usbpcap2.pcap"
    tool = root.parent / "win11-capture/tools/usbpcap_decode.py"
    if not pcap.exists() or not tool.exists():
        pytest.skip("private capture absent")
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("usbdec", tool)
    dec = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = dec
    try:
        spec.loader.exec_module(dec)
    finally:
        sys.modules.pop(spec.name, None)
    captured = wire_commands(bytes(dec.decode(pcap).tx))
    first_read = next(i for i, c in enumerate(captured) if c[:1] == H("06"))
    head = [c for i, c in enumerate(captured[:first_read]) if not (c == H("08") and captured[i - 1] == H("08"))]
    dev, _, s = make()
    s.open()
    assert sent(dev)[:len(head)] == head    # PC-Tool sends identify twice; we send it once


def test_engine_opens_session_for_writes_and_closes_it_on_detach(synthetic_mapping, tmp_path):
    from helixtune.engine import Engine
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    dev = EmulatedDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.05), "emulator")
    assert dev.session_open and dev.device_baud == HIGH
    engine.detach()
    assert not dev.session_open and dev.device_baud == LOW and dev.baudrate == LOW


def test_read_only_attach_never_starts_a_session(synthetic_mapping, tmp_path):
    from helixtune.engine import Engine
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    dev = EmulatedDevice()
    engine.attach(Client(dev, timeout=0.05), "emulator")
    assert sent(dev) == [H("08")] and engine.session is None


def test_keepalive_pings_and_marks_a_silent_dsp_uncertain(synthetic_mapping, tmp_path):
    import time
    from helixtune.engine import Engine
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path, keepalive_s=0.02)
    dev = EmulatedDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.02), "emulator")
    assert wait_for(lambda: sum(1 for c in sent(dev) if c[:1] == H("02")) >= 3)
    dev.baudrate = LOW                        # simulate the link dropping out of sync
    assert wait_for(lambda: engine.device.sync_state == "uncertain")
    assert "keep-alive" in engine.device.last_error
    engine.detach()


def test_missed_keepalive_invalidates_baseline_and_stops_incremental_writes(synthetic_mapping, tmp_path):
    """Codex review P1: after a missed echo, zero incremental 03 traffic until a deliberate full overwrite."""
    import time
    from helixtune.engine import Engine
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path, keepalive_s=0.02)
    dev = EmulatedDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.02), "emulator")
    engine.push_full("OVERWRITE")
    assert engine.device.baselined
    dev.baudrate = LOW                                   # link drops out of sync
    assert wait_for(lambda: engine.device.sync_state == "uncertain")
    assert not engine.device.baselined
    assert engine.applied_image is None and engine.pending_writes > 0
    before = len(dev.log)
    result = engine.edit("test", "gain", lambda t: setattr(t.channel("A"), "gain_db", -3.0))
    assert result.get("writes", 0) == 0
    assert not [c for c in wire_commands(b"".join(dev.log[before:])) if c[:1] == H("03")]
    engine.detach()


def test_attach_recovers_a_dsp_left_at_high_speed(synthetic_mapping, tmp_path):
    """Codex review P2: Session.open owns first contact so its baud recovery runs before identify."""
    from helixtune.engine import Engine
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    dev = EmulatedDevice()
    dev.device_baud = HIGH
    engine.attach(Client(dev, allow_writes=True, timeout=0.05), "emulator")
    assert dev.session_open and engine.device.model
    engine.detach()
    assert dev.device_baud == LOW


def test_drain_is_bounded_on_a_chattering_line():
    class Chatter(Recording):
        def read(self, size): return b"\x55" * size
    from helixtune.protocol.client import Client as C
    got = C(EmulatedDevice()).drain()                    # quiet line: returns at once
    assert got == b""
    c = C(Chatter())
    assert len(c.drain()) <= C.DRAIN_MAX_BYTES + 256


def test_every_sync_burst_is_followed_by_the_post_sync_pause():
    """2026-10-18 live test: without ~0.1 s after a sync burst the first command at the new
    rate went unanswered and the session failed to open."""
    from helixtune.protocol import frame
    from helixtune.protocol.session import POST_SYNC_S
    dev, events = EmulatedDevice(), []
    write = dev.write
    dev.write = lambda data: (events.append("SYNC" if bytes(data) == frame.SYNC_FRAME else "cmd"), write(data))[1]

    def set_baud(b):
        dev.baudrate = b
    s = Session(Client(dev, allow_writes=True, timeout=0.05), set_baud, sleep=events.append)
    s.open()
    s.close()
    syncs = [i for i, e in enumerate(events) if e == "SYNC"]
    assert len(syncs) == 5 and POST_SYNC_S >= 0.1          # 4 in open, 1 in close
    assert all(events[i + 1] == POST_SYNC_S for i in syncs)


class BadEcho(EmulatedDevice):
    """Answers everything like the DSP but corrupts the keep-alive echo."""
    def _handle(self, p):
        reply = super()._handle(p)
        return bytes([0x02, 0x00]) + bytes(6) if p[:1] == b"\x02" and reply is not None else reply


def test_a_partial_open_closes_the_session_and_returns_to_19200():
    dev, bauds, s = make(BadEcho())
    with pytest.raises(SessionError, match="keep-alive not echoed"):
        s.open()
    wire = sent(dev)
    assert wire[-3:] == [H("09 00"), H("0a 2f"), b"SYNC"] and wire.count(H("09 00")) == 1
    assert not dev.session_open and dev.device_baud == LOW and bauds[-1] == LOW and not s.open_


def test_an_unrecognised_device_gets_nothing_after_identify():
    payload = bytearray(EmulatedDevice().identify_payload)
    payload[142:150] = b"OTHERDEV"
    dev, _, s = make(EmulatedDevice(identify_payload=bytes(payload)))
    with pytest.raises(SessionError):
        s.open()
    assert sent(dev)[-1] == H("08")                      # no session start, no close


def test_engine_attach_partial_open_closes_once_and_reports(synthetic_mapping, tmp_path):
    from helixtune.engine import Engine, EngineError
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    dev = BadEcho()
    with pytest.raises(EngineError, match="keep-alive not echoed"):
        engine.attach(Client(dev, allow_writes=True, timeout=0.05), "emulator")
    assert sent(dev).count(H("09 00")) == 1 and not dev.session_open and dev.device_baud == LOW
    assert engine.client is None and engine.session is None


def test_missed_keepalive_requires_reconnect_even_for_a_full_overwrite(synthetic_mapping, tmp_path):
    from helixtune.engine import Engine, EngineError
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path, keepalive_s=0.02)
    dev = EmulatedDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.02), "emulator")
    dev.baudrate = LOW                                   # link drops out of sync
    assert wait_for(lambda: engine.device.needs_reconnect)
    before = len(dev.log)
    with pytest.raises(EngineError, match="disconnect and reconnect"):
        engine.push_full("OVERWRITE")
    assert not [c for c in wire_commands(b"".join(dev.log[before:])) if c[:1] == H("03")]
    engine.detach()
    dev2 = EmulatedDevice()
    engine.attach(Client(dev2, allow_writes=True, timeout=0.05), "emulator")
    assert not engine.device.needs_reconnect and engine.push_full("OVERWRITE") > 0
    engine.detach()


def test_physical_ports_need_a_short_read_timeout():
    class Port(Recording):
        def __init__(self, timeout): super().__init__(); self.timeout = timeout
    for bad in (None, 1.0):
        with pytest.raises(ValueError, match="read timeout"):
            Client(Port(bad))
    Client(Port(0.05))
    Client(Recording())                                  # fakes without a timeout attribute
