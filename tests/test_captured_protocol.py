"""Capture-derived command structure, synthetic addresses and fake transports only."""
import pytest

from conftest import owner_client
from helixtune.api import create_app
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.protocol import commands, frame
from helixtune.protocol.client import Client, WritesDisabled


class RecordingTransport:
    def __init__(self): self.log = []
    def reset_input_buffer(self): self.log.append('reset')
    def write(self, data): self.log.append(data); return len(data)
    def read(self, size): return b''


def test_parameter_write_matches_independent_wire_literal():
    assert commands.write_ram(0x1234, bytes.fromhex('01 02 03 04')) == bytes.fromhex('03 00 01 12 34 01 02 03 04')
    assert frame.encode_tx(commands.write_ram(0x1234, bytes.fromhex('01 02 03 04'))) == bytes.fromhex('42 0a f5 01 03 00 01 12 34 01 02 03 04 54')
    assert len(EmulatedDevice().identify_payload) == 174
    assert frame.SYNC_FRAME == bytes.fromhex('42 00') * 10


@pytest.mark.parametrize('size', [0, 1, 3, 5, 249, 252])
def test_only_complete_bounded_words_are_encoded(size):
    with pytest.raises(ValueError): commands.write_ram(0, bytes(size))


def test_parameter_writes_cannot_wrap_address_space():
    with pytest.raises(ValueError): commands.write_ram(0xffff, bytes(8))


@pytest.mark.parametrize('opcode', [0x02, 0x03, 0x04, 0x05, 0x09, 0x0a, 0x32, 0xff])
def test_physical_commands_other_than_identify_blocked_before_transport_io(opcode):
    transport = RecordingTransport()
    with pytest.raises(WritesDisabled):
        Client(transport, allow_writes=True).transact(bytes([opcode, 0, 1]))
    assert transport.log == []


@pytest.mark.parametrize('method', ['builder', 'client'])
def test_unestablished_ram_read_never_sends_preset_storage_commands(method):
    transport = RecordingTransport()
    with pytest.raises(NotImplementedError):
        if method == 'builder': commands.read_ram(0x1234, 4)
        else: Client(transport, allow_writes=True).read_ram(0x1234, 4)
    assert not transport.log


@pytest.mark.parametrize('payload,channel', [
    (bytes.fromhex('03 00 01 12 35'), 1),
    (bytes.fromhex('03 00 02 12 34'), 1),
    (bytes.fromhex('05 00 01 12 34'), 1),
    (bytes.fromhex('03 00 01 12 34 00'), 1),
    (bytes.fromhex('03 00 01 12 34'), 2),
])
def test_write_ack_must_match_command_bank_address_and_frame_channel(payload, channel):
    class BadAck(EmulatedDevice):
        def write(self, data):
            count = super().write(data)
            self._out = bytearray(frame.encode_rx(payload, channel=channel))
            return count
    with pytest.raises(frame.FrameError, match='acknowledgement'):
        Client(BadAck(), allow_writes=True).write_ram(0x1234, bytes(4))


def test_engine_and_api_refuse_physical_write_enable_before_identify_or_open(tmp_path, synthetic_mapping, monkeypatch):
    import serial
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    transport = RecordingTransport()
    with pytest.raises(EngineError, match='Physical writes are disabled'):
        engine.attach(Client(transport, allow_writes=True), 'serial')
    assert not transport.log
    engine.attach(Client(EmulatedDevice()), 'emulator')
    def forbidden(*args, **kwargs): pytest.fail('physical port must not open')
    monkeypatch.setattr(serial, 'Serial', forbidden)
    with owner_client(create_app(engine)) as client:
        assert client.post('/api/device/connect', json={'port':'test-port','allow_writes':True}).status_code == 400
    assert engine.device.kind == 'emulator'  # rejected request does not detach current connection


def test_fixed_crossover_banks_keep_lp_at_stage3_when_hp_is_bypassed(synthetic_mapping):
    from helixtune.model import Tune, Crossover
    from helixtune.dsp.filters import XoType
    tune = Tune()
    tune.channel('A').lp = Crossover(type=XoType.LINKWITZ_RILEY, slope_db=24, freq_hz=400)
    image = synthetic_mapping.render(tune)
    identity = {'B2': bytes(4), 'B1': bytes(4), 'B0': bytes.fromhex('01000000'), 'A2': bytes(4), 'A1': bytes(4)}
    slots = synthetic_mapping.channels[0].xo_bq
    for index in (0, 1, 2, 5, 6):
        assert {key: image[address] for key,address in slots[index].items()} == identity
    assert image[slots[3]['B0']] != identity['B0']
    assert {key:image[address] for key,address in slots[3].items()} == {key:image[address] for key,address in slots[4].items()}


def test_unestablished_48db_bank_layout_refused_instead_of_borrowing_lp_slots(synthetic_mapping):
    from helixtune.model import Tune, Crossover
    from helixtune.mapping import MappingError
    tune = Tune()
    tune.channel('A').hp = Crossover(slope_db=48, freq_hz=70)
    with pytest.raises(MappingError, match='fixed bank'):
        synthetic_mapping.render(tune)


def test_pc_tool_kernel_profile_is_explicit_and_generic_filter_math_stays_ideal():
    from helixtune.dsp import filters as F
    bqs, _ = F.crossover_sections(F.XoType.LINKWITZ_RILEY,24,400,96000,False,pc_tool_q=True)
    assert bqs == [F._lp2(400,0.707,96000)] * 2
    ideal, _ = F.crossover_sections(F.XoType.LINKWITZ_RILEY,24,400,96000,False)
    assert bqs != ideal


@pytest.mark.parametrize('opcode', [4, 5])
def test_preset_storage_opcodes_remain_blocked_even_on_write_enabled_emulator(opcode):
    device = EmulatedDevice()
    with pytest.raises(WritesDisabled, match='preset-storage'):
        Client(device, allow_writes=True).transact(bytes([opcode, 0, 0, 4]))
    assert not device.log


def test_824_truncates_toward_zero_like_pc_tool():
    """Words PC-Tool sent on 2026-10-17 (gain +2 dB; EQ peak 25 Hz +3 dB Q4.3 @96 kHz,
    stored B2,B1,B0,-A2,-A1). round() gives 0x014248f0 for the gain and is 1 LSB off on
    several coefficients; truncation toward zero reproduces every captured word."""
    from helixtune.dsp.filters import EqType, eq_biquad
    from helixtune.dsp.fixed import word_824
    assert word_824(10 ** (2 / 20)) == bytes.fromhex('01 42 48 ef')
    b = eq_biquad(EqType.PEAK, 25.0, 3.0, 4.3, 96000.0)
    words = b''.join(word_824(v) for v in (b.b2, b.b1, b.b0, -b.a2, -b.a1))
    assert words == bytes.fromhex('00ffe6b1 fe001528 01000453 ff0014fb 01ffead8')
    assert word_824(-1e-9) == bytes(4)          # toward zero, not floor (which gives ffffffff)


def test_butterworth_12_uses_pc_tool_q_071_bit_exact():
    """Capture 23 (2026-10-18), output A HP Butterworth 12 dB at 60.83 Hz, stage 0 words."""
    from helixtune.dsp import filters as F
    from helixtune.dsp.fixed import word_824
    (bq,), fos = F.crossover_sections(F.XoType.BUTTERWORTH, 12, 60.83, 96000, True, pc_tool_q=True)
    words = {"B2": bq.b2, "B1": bq.b1, "B0": bq.b0, "A2": -bq.a2, "A1": -bq.a1}
    captured = {"B2": "00ff4882", "B1": "fe016efc", "B0": "00ff4882", "A2": "ff016e77", "A1": "01fe9080"}
    assert not fos and {k: word_824(v).hex() for k, v in words.items()} == captured
