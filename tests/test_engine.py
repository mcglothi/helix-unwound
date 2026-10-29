from pathlib import Path

import pytest

from helixtune import mapping
from helixtune.devicefile import load_at01
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError, SafetyRejected
from helixtune.model import Crossover, Role
from helixtune.protocol.client import Client

AT01 = Path(__file__).resolve().parents[1] / "artifacts/extracted/app/deviceFiles/DSPPro2.at01"
pytestmark = pytest.mark.skipif(not AT01.exists(), reason="vendor device files not extracted")


@pytest.fixture
def eng(tmp_path):
    return Engine.from_param_map(load_at01(AT01), tmp_path)


def live(eng):
    dev = EmulatedDevice()
    eng.attach(Client(dev, allow_writes=True), "emulator")
    eng.push_full(confirm="OVERWRITE")
    return dev


def test_no_writes_until_full_push_confirmed(eng):
    dev = EmulatedDevice()
    eng.attach(Client(dev, allow_writes=True), "emulator")
    n_before = len(dev.log)
    eng.edit("test", "boost", lambda t: setattr(t.channel("A"), "gain_db", -3))
    assert len(dev.log) == n_before  # identify only; nothing written
    with pytest.raises(EngineError):
        eng.push_full(confirm="yes")


def test_single_band_change_writes_one_block(eng):
    dev = live(eng)
    before = len(dev.log)

    def f(t):
        b = t.channel("B").eq[4]
        b.enabled, b.gain_db, b.freq_hz = True, -4.0, 250
    res = eng.edit("test", "cut B band 5", f)
    assert res["writes"] == 1 and len(dev.log) == before + 1


def test_tweeter_without_highpass_rejected(eng):
    live(eng)
    with pytest.raises(SafetyRejected) as ei:
        eng.edit("agent", "tweeter", lambda t: setattr(t.channel("A"), "role", Role.TWEETER))
    assert "high-pass filter required" in str(ei.value)
    assert eng.tune.channel("A").role is Role.UNUSED  # state unchanged


def test_big_boost_step_rejected_then_allowed_in_steps(eng):
    live(eng)

    def set_boost(db):
        def f(t):
            b = t.channel("C").eq[0]
            b.enabled, b.gain_db = True, db
        return f
    eng.edit("agent", "role", lambda t: setattr(t.channel("C"), "role", Role.FULLRANGE))
    with pytest.raises(SafetyRejected):
        eng.edit("agent", "+6", set_boost(6))
    eng.edit("agent", "+3", set_boost(3))
    eng.edit("agent", "+6", set_boost(6))
    assert eng.tune.channel("C").eq[0].gain_db == 6


def test_crossover_capacity_enforced(eng):
    def f(t):
        ch = t.channel("D")
        ch.hp = Crossover(type="linkwitz_riley", slope_db=48, freq_hz=80)
        ch.lp = Crossover(type="linkwitz_riley", slope_db=48, freq_hz=500)
    with pytest.raises(mapping.MappingError):
        eng.edit("test", "too steep", f)


def test_undo_restores_device_ram(eng):
    dev = live(eng)
    ad = eng.mapping.channels[0].gain
    orig = bytes(dev.ram[ad * 4 : ad * 4 + 4])
    eng.edit("test", "gain", lambda t: setattr(t.channel("A"), "gain_db", -10))
    assert bytes(dev.ram[ad * 4 : ad * 4 + 4]) != orig
    eng.undo()
    assert bytes(dev.ram[ad * 4 : ad * 4 + 4]) == orig


def test_state_persists_across_restart(eng, tmp_path):
    eng.edit("test", "name", lambda t: setattr(t.channel("E"), "name", "Sub L"))
    again = Engine.from_param_map(load_at01(AT01), tmp_path)
    assert again.tune.channel("E").name == "Sub L"


def test_mix_written_to_main_matrix_row_like_pc_tool(eng):
    """Captures 23/24: PC-Tool writes MAINMATRIX VOL08{00..11} for output I, L/R in inputs 0/1."""
    dev = live(eng)
    ad = eng.mapping.channels[8].mix  # channel I
    assert [eng.mapping.pm.name_at(ad[k])[0][-7:] for k in ("L", "R")] == ["VOL0800", "VOL0801"]
    assert len(ad) == 12 and all(eng.mapping.pm.name_at(a)[0].startswith("MAINMATRIX_") for a in ad.values())
    eng.edit("test", "sub 40/50", lambda t: setattr(t.channel("I"), "mix", {"L": 0.4, "R": 0.5}))
    word = lambda a: bytes(dev.ram[a * 4: a * 4 + 4]).hex()
    assert (word(ad["L"]), word(ad["R"])) == ("00666666", "00800000")      # captured words
    assert all(word(a) == "00000000" for k, a in ad.items() if k not in ("L", "R"))
    with pytest.raises(Exception):
        eng.edit("test", "bad", lambda t: setattr(t.channel("I"), "mix", {"X": 1.0}))
