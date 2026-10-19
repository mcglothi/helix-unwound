"""2026-10-18 live findings: the backup session gate and the Director-volume write guard."""
import pytest

from helixtune.devicefile import ParamMap
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.mapping import PROTECTED_PATTERN
from helixtune.protocol import commands
from helixtune.protocol.client import Client, WritesDisabled
from helixtune.dsp.filters import EqType, XoType
from helixtune.model import Crossover, EqBand


class Physical:
    """Stands in for a serial port: anything that is not the emulator is physical."""
    def __init__(self): self.log = []
    def reset_input_buffer(self): pass
    def write(self, data): self.log.append(bytes(data)); return len(data)
    def read(self, size): return b""


def test_backup_mode_admits_only_the_backup_session_and_never_writes():
    t = Physical()
    c = Client(t, allow_writes=True)
    with pytest.raises(WritesDisabled):
        c.send(commands.SESSION_START)                       # outside backup mode
    with pytest.raises(WritesDisabled):
        c.send_sync()
    with c.stored_backup_mode():
        c.send(commands.SESSION_START)
        c.send_sync()
        c.send(commands.SELECT_STORED)
        for refused in (commands.write_ram(0x232C, bytes(4)), bytes.fromhex("32 01 05 00"),
                        bytes.fromhex("32 0f 00 00 02 00 00"), bytes.fromhex("05 ff fe 01 06"),
                        bytes.fromhex("04 00 00 12") + bytes(18)):
            with pytest.raises(WritesDisabled):
                c.send(refused)
    with pytest.raises(WritesDisabled):
        c.send(commands.SELECT_STORED)                       # mode ends with the context
    assert len(t.log) == 3


def test_protected_pattern_matches_director_volumes_and_nothing_tunable():
    names = {
        "URC_FUNCTION_OPTOVOLUMEVALUE_DCINPALG145X9VALUE": 1, "URC_FUNCTION_MASTERVOLUMEVALUE_DCINPALG145X6VALUE": 2,
        "URC_FUNCTION_SUBVOLUME_MONOMUXSIGMA300NS23INDEX": 3, "URC_FUNCTION_AUXVOLUMEVALUE_DCINPALG145X10VALUE": 4,
        "OPTO_MATRIX_OPTOVOLUMEURC_SLEW_MODE": 5, "MASTERVOLUME_SLEW_MODE": 6, "MASTERVOLUMEOPTOOUT_SLEW_MODE": 7,
        "GAIN_GAINA_GAINALGNS145X14GAIN": 10, "GAIN1_GAINALGNS145X1GAIN": 11,
        "OPTO_MATRIX_OPTOMIXER_ALG0_NXNMIXERS300ALG1VOL0000": 12, "URC_FUNCTION_SPDIFSWITCH_DCINPALG145X19VALUE": 13,
    }
    hits = set(ParamMap(params=names).find(PROTECTED_PATTERN).values())
    assert hits == {1, 2, 3, 4, 5, 6, 7}


def test_engine_refuses_a_render_that_touches_a_protected_address(synthetic_mapping, tmp_path):
    synthetic_mapping.protected = frozenset({synthetic_mapping.channels[0].gain})
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    dev = EmulatedDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.05), "emulator")
    before = len(dev.log)
    with pytest.raises(EngineError, match="Director/remote volume"):
        engine.push_full("OVERWRITE")
    assert not [raw for raw in dev.log[before:] if raw[3:4] == b"\x03"]   # no parameter write left
    engine.detach()


def test_real_device_map_protects_digital_volume_if_available():
    from helixtune.cli import find_param_map
    from helixtune.devicefile import load_at01
    from helixtune.mapping import DeviceMapping
    from helixtune.model import Tune
    try:
        at01 = find_param_map(None)
    except SystemExit:
        pytest.skip("vendor device file absent")
    m = DeviceMapping(load_at01(at01))
    assert 0x22F9 in m.protected and len(m.protected) == 12
    assert not set(m.render(Tune())) & m.protected


class PhysicalDsp:
    """A real-port stand-in (not an EmulatedDevice) that speaks the protocol via an emulator."""
    def __init__(self):
        object.__setattr__(self, "dev", EmulatedDevice())
    def reset_input_buffer(self): self.dev.reset_input_buffer()
    def write(self, data): return self.dev.write(data)
    def read(self, size): return self.dev.read(size)
    def __getattr__(self, name): return getattr(self.dev, name)
    def __setattr__(self, name, value): setattr(self.dev, name, value)   # baudrate set by the session


@pytest.fixture
def quick_session(monkeypatch):
    from helixtune.protocol import session
    for name in ("SETTLE_S", "ACK_WAIT_S", "POST_SYNC_S"):
        monkeypatch.setattr(session, name, 0)


def test_physical_writes_stay_refused_without_the_opt_in(synthetic_mapping, tmp_path, quick_session):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    port = PhysicalDsp()
    with pytest.raises(EngineError, match="--allow-physical-writes"):
        engine.attach(Client(port, allow_writes=True, physical_session=True, timeout=0.05), "serial", "x")
    engine.physical_writes_allowed = True
    with pytest.raises(EngineError, match="--allow-physical-writes"):      # needs the session client too
        engine.attach(Client(port, allow_writes=True, timeout=0.05), "serial", "x")
    assert port.dev.log == []                                               # nothing reached the port


def test_opted_in_physical_session_writes_parameters_and_nothing_else(synthetic_mapping, tmp_path, quick_session):
    from helixtune.protocol.session import wire_commands
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    engine.physical_writes_allowed = True
    port = PhysicalDsp()
    client = Client(port, allow_writes=True, physical_session=True, timeout=0.05)
    engine.attach(client, "serial", "x")
    assert port.dev.session_open and port.dev.device_baud == commands.HIGH_HOST_BAUD
    assert engine.push_full("OVERWRITE") > 0
    for refused in (bytes.fromhex("05 ff fe 01 06"), bytes.fromhex("04 00 00 12") + bytes(18),
                    bytes.fromhex("13 00 40") + bytes(65), bytes.fromhex("17 04 00"),
                    bytes.fromhex("1b 06 00 00 00 00 00 00"), bytes.fromhex("32 0f 00 00 02 00 00"),
                    bytes.fromhex("32 01 05 00")):
        with pytest.raises(WritesDisabled):
            client.send(refused)
    engine.detach()
    kinds = {c[:1] for c in wire_commands(b"".join(port.dev.log)) if c != b"SYNC"}
    assert kinds <= {b"\x08", b"\x09", b"\x0a", b"\x02", b"\x03"}
    assert not port.dev.session_open and port.dev.device_baud == commands.LOW_HOST_BAUD


def test_cli_serve_flag_defaults_off(monkeypatch, synthetic_mapping, tmp_path):
    import uvicorn
    from helixtune import api, cli, devicefile
    engines = []
    monkeypatch.setattr(cli, "find_param_map", lambda explicit: "unused")
    monkeypatch.setattr(devicefile, "load_at01", lambda path: None)
    monkeypatch.setattr(Engine, "from_param_map", classmethod(lambda cls, pm, data: Engine(mapping=synthetic_mapping, data_dir=tmp_path)))
    monkeypatch.setattr(api, "create_app", lambda engine: engines.append(engine))
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert cli.main(["serve", "--data", str(tmp_path)]) == 0
    assert cli.main(["serve", "--data", str(tmp_path), "--allow-physical-writes"]) == 0
    assert [e.physical_writes_allowed for e in engines] == [False, True]


def _physical_engine(synthetic_mapping, tmp_path):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    engine.physical_writes_allowed = True
    port = PhysicalDsp()
    engine.attach(Client(port, allow_writes=True, physical_session=True, timeout=0.05), "serial", "x")
    return engine, port


def _param_writes(port, since=0):
    from helixtune.protocol.session import wire_commands
    return [c for c in wire_commands(b"".join(port.dev.log[since:])) if c[:1] == b"\x03"]


@pytest.mark.parametrize("change", [
    lambda t: setattr(t.channel("A"), "hp", Crossover(type=XoType.BESSEL, slope_db=24, freq_hz=60)),
    lambda t: setattr(t.channel("A"), "hp", Crossover(type=XoType.LINKWITZ_RILEY, slope_db=36, freq_hz=60)),
    lambda t: setattr(t.channel("A"), "lp", Crossover(type=XoType.BUTTERWORTH, slope_db=12, freq_hz=2000)),
    lambda t: t.channel("A").eq.__setitem__(0, EqBand(enabled=True, type=EqType.LOW_SHELF, freq_hz=80, gain_db=3, q=0.7)),
])
def test_unverified_settings_send_zero_parameter_writes_to_a_real_dsp(synthetic_mapping, tmp_path, quick_session, change):
    engine, port = _physical_engine(synthetic_mapping, tmp_path)
    t = engine.tune.model_copy(deep=True)
    change(t)
    engine.tune = t
    review = engine.overwrite_review()
    assert review["physical"] and review["ineligible"]
    before = len(port.dev.log)
    with pytest.raises(EngineError, match="not verified against PC-Tool"):
        engine.push_full("OVERWRITE")
    assert _param_writes(port, before) == [] and not engine.device.baselined
    engine.detach()


def test_provisional_master_is_never_written_to_a_real_dsp(synthetic_mapping, tmp_path, quick_session):
    engine, port = _physical_engine(synthetic_mapping, tmp_path)
    assert engine.overwrite_review()["excluded"]
    engine.push_full("OVERWRITE")
    master = synthetic_mapping.master
    covered = lambda c: int.from_bytes(c[3:5], "big") <= master < int.from_bytes(c[3:5], "big") + (len(c) - 5) // 4
    assert _param_writes(port) and not [c for c in _param_writes(port) if covered(c)]
    before = len(port.dev.log)
    result = engine.edit("test", "master", lambda t: setattr(t, "master_gain_db", -6.0))
    assert result["writes"] == 0 and _param_writes(port, before) == []          # baseline excludes it
    with pytest.raises(EngineError, match="not verified"):
        engine.edit("test", "bessel", lambda t: setattr(t.channel("B"), "hp", Crossover(type=XoType.BESSEL, slope_db=12, freq_hz=80)))
    assert engine.tune.channel("B").hp is None and _param_writes(port, before) == []
    engine.detach()


def test_emulator_still_models_master_and_every_filter(synthetic_mapping, tmp_path):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    dev = EmulatedDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.05), "emulator")
    engine.tune.channel("A").hp = Crossover(type=XoType.BESSEL, slope_db=24, freq_hz=60)
    review = engine.overwrite_review()
    assert not review["physical"] and review["ineligible"] == [] and review["excluded"] == []
    assert engine.push_full("OVERWRITE") > 0
    assert bytes(dev.ram[synthetic_mapping.master * 4: synthetic_mapping.master * 4 + 4]) != bytes(4)
    engine.detach()


def test_status_reports_the_physical_write_capability(synthetic_mapping, tmp_path):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    assert engine.status()["physical_writes_allowed"] is False
    engine.physical_writes_allowed = True
    assert engine.status()["physical_writes_allowed"] is True


def test_master_is_workstation_only_on_a_real_dsp_including_predictions(synthetic_mapping, tmp_path, quick_session):
    """Codex follow-up: master is excluded from physical images, so it must not look applied."""
    import numpy as np
    from helixtune.measurements import GRID, Measurement
    from helixtune.model import Tune
    captured = Tune()
    m = Measurement(name="flat", channels=["A"], freqs=[20.0, 20000.0], spl=[80.0, 80.0], tune=captured)
    now = Tune(master_gain_db=-6.0)
    from helixtune import measurements
    assert np.allclose(measurements.predict(m, now, GRID) - measurements.predict(m, now, GRID, include_master=False), -6.0)

    emu = Engine(mapping=synthetic_mapping, data_dir=tmp_path / "emu")
    emu.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), "emulator")
    assert emu.status()["master_on_device"] is True and np.allclose(emu._predict(m, now, GRID)[0], 74.0)
    emu.detach()

    engine, port = _physical_engine(synthetic_mapping, tmp_path / "hw")
    assert engine.status()["master_on_device"] is False
    assert np.allclose(engine._predict(m, now, GRID), 80.0)                  # master change not shown as acoustic
    engine.detach()
    assert engine.status()["master_on_device"] is True                       # offline editing models it again
