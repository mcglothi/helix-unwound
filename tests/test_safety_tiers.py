"""Red/yellow/green high-pass protection tiers.

Red (blocks): role floors and manufacturer-published limits; the Fs-multiple margin when the
manufacturer publishes no minimum. Yellow (allowed, reported): the Fs-multiple margin of a
driver whose manufacturer minimum is lower. Synthetic drivers only.
"""
from helixtune import protection_provenance as provenance, safety
from helixtune.equipment import DriverLimits
from helixtune.model import Crossover, Role, Tune
from helixtune.dsp.filters import XoType

POLICY = safety.SafetyPolicy()   # midrange: role floor 150 Hz, fs_factor 1.5


def mid_tune(hp_hz: float) -> Tune:
    t = Tune()
    ch = t.channel("C")
    ch.role = Role.MIDRANGE
    ch.hp = Crossover(type=XoType.LINKWITZ_RILEY, slope_db=24, freq_hz=hp_hz)
    return t


WITH_MAKER_MIN = {"C": DriverLimits(label="mid", fs=170.0, hp_min=200.0, hp_min_slope=12)}
FS_ONLY = {"C": DriverLimits(label="mid", fs=170.0)}


def test_between_maker_minimum_and_fs_margin_is_yellow_not_red():
    t = mid_tune(220.0)
    assert safety.check(t, POLICY, driver_limits=WITH_MAKER_MIN) == []
    notes = safety.advisories(t, POLICY, driver_limits=WITH_MAKER_MIN)
    assert len(notes) == 1 and "255" in notes[0] and "200" in notes[0]


def test_below_maker_minimum_is_red_and_above_margin_is_green():
    assert any("200" in p for p in safety.check(mid_tune(190.0), POLICY, driver_limits=WITH_MAKER_MIN))
    green = mid_tune(260.0)
    assert safety.check(green, POLICY, driver_limits=WITH_MAKER_MIN) == []
    assert safety.advisories(green, POLICY, driver_limits=WITH_MAKER_MIN) == []


def test_fs_margin_stays_enforced_without_a_manufacturer_minimum():
    problems = safety.check(mid_tune(220.0), POLICY, driver_limits=FS_ONLY)
    assert any("255" in p for p in problems)
    assert safety.advisories(mid_tune(220.0), POLICY, driver_limits=FS_ONLY) == []


def _book(with_maker_min: bool) -> provenance.ProtectionBook:
    driver = {"id": "d1", "make": "Maker", "model": "M", "serial": "", "kind": "speaker", "channels": ["C"]}
    items = [provenance.candidate("C", "min_hp_hz", 255.0, {"kind": "equipment", "driver": driver, "spec_key": "fs",
                                                              "spec": {"value": 170.0, "unit": "Hz"}, "factor": 1.5})]
    if with_maker_min:
        items.append(provenance.candidate("C", "min_hp_hz", 200.0, {"kind": "equipment", "driver": driver,
                                                                    "spec_key": "hp_min", "spec": {"value": 200.0, "unit": "Hz"}}))
    return provenance.ProtectionBook(constraints={i.id: i for i in items})


def test_recorded_fs_margin_is_advisory_only_beside_a_live_maker_minimum():
    book = _book(with_maker_min=True)
    assert book.effective().outputs["C"].min_hp_hz == 200.0
    assert book.effective(include_advisory=True).outputs["C"].min_hp_hz == 255.0
    # clearing the manufacturer minimum makes the Fs margin the enforced floor again
    maker = next(i for i in book.constraints.values() if i.source["spec_key"] == "hp_min")
    maker.state = "cleared"
    assert book.effective().outputs["C"].min_hp_hz == 255.0
    assert _book(with_maker_min=False).effective().outputs["C"].min_hp_hz == 255.0


def test_status_and_safety_check_report_advisories(synthetic_mapping, tmp_path):
    from conftest import owner_client
    from helixtune.api import create_app
    from helixtune.engine import Engine
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    with owner_client(create_app(engine)) as c:
        assert c.get("/api/status").json()["advisories"] == []
        body = c.get("/api/safety/check").json()
        assert body["problems"] == [] and body["advisories"] == []
