"""2026-10-18 live findings: the backup session gate and the Director-volume write guard."""
import pytest

from helixtune.devicefile import ParamMap
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.mapping import PROTECTED_PATTERN
from helixtune.protocol import commands
from helixtune.protocol.client import Client, WritesDisabled


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
