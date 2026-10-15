import json

import pytest
from pydantic import ValidationError

from helixtune import equipment, safety
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError, SafetyRejected
from helixtune.model import Crossover, Role
from helixtune.proposals import Edit, Proposal
from helixtune.protocol.client import Client


@pytest.fixture
def engine(tmp_path, synthetic_mapping):
    return Engine(mapping=synthetic_mapping, data_dir=tmp_path)


def protect_tweeter(engine):
    def configure(t):
        t.channel("A").hp = Crossover(freq_hz=3000)
        t.channel("A").role = Role.TWEETER
    engine.edit("test", "set up tweeter", configure)


def test_role_changes_cannot_remove_physical_protection(engine):
    protect_tweeter(engine)
    engine.edit("agent", "rename role", lambda t: setattr(t.channel("A"), "role", Role.UNUSED))
    with pytest.raises(SafetyRejected, match="high-pass filter required"):
        engine.edit("agent", "remove high-pass", lambda t: setattr(t.channel("A"), "hp", None))
    assert engine.protections.outputs["A"].min_hp_hz == 1500


def test_muting_does_not_erase_limits_and_unmuting_is_checked(engine):
    protect_tweeter(engine)
    def park(t):
        ch = t.channel("A")
        ch.mute, ch.role, ch.hp = True, Role.UNUSED, None
    engine.edit("test", "mute and stage", park)
    with pytest.raises(SafetyRejected):
        engine.edit("test", "unmute", lambda t: setattr(t.channel("A"), "mute", False))
    assert engine.protections.outputs["A"].min_hp_hz == 1500


def test_unused_label_cannot_bypass_gain_or_eq_ceiling(engine):
    draft = engine.tune.model_copy(deep=True)
    draft.channel("A").gain_db = 7
    draft.channel("A").eq[0].enabled = True
    draft.channel("A").eq[0].gain_db = 10
    problems = engine._check(draft)
    assert any("gain 7" in p and "exceeds" in p for p in problems)
    assert any("boost 10" in p and "exceeds" in p for p in problems)


@pytest.mark.parametrize("operation", ["snapshot", "undo", "ab", "proposal", "replace", "full_push"])
def test_every_tune_adoption_path_enforces_saved_floors(engine, operation):
    original = engine.tune.model_copy(deep=True)
    engine.save_snapshot("unprotected")
    engine.ab_set("B", "unprotected")
    protect_tweeter(engine)
    engine.ab_set("A", None)
    with pytest.raises(SafetyRejected):
        if operation == "snapshot":
            engine.load_snapshot("unprotected", "test")
        elif operation == "undo":
            engine.undo()
        elif operation == "ab":
            engine.ab_toggle("test")
        elif operation == "proposal":
            # a correctly bound proposal (before-value matches), so protection is what rejects it
            proposal = Proposal(kind="test", title="remove high-pass", edits=[
                Edit(channel="A", field="hp", value=None, before=engine.tune.channel("A").hp)])
            engine.proposals[proposal.id] = proposal
            engine.apply_proposal(proposal.id, "agent")
        elif operation == "replace":
            engine.apply(original, "agent", "replace tune")
        else:
            device = EmulatedDevice()
            engine.attach(Client(device, allow_writes=True), "emulator")
            engine.tune = original
            engine.push_full("OVERWRITE")
    if operation == "full_push":
        assert len(device.log) == 1  # identify only; rejected before writing


def test_protections_survive_restart_after_metadata_change(engine, synthetic_mapping):
    protect_tweeter(engine)
    engine.edit("test", "relabel", lambda t: setattr(t.channel("A"), "role", Role.UNUSED))
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.protections.outputs["A"].min_hp_hz == 1500
    with pytest.raises(SafetyRejected):
        again.edit("test", "remove high-pass", lambda t: setattr(t.channel("A"), "hp", None))


def test_legacy_tune_migrates_without_changing_the_tune(tmp_path, synthetic_mapping):
    initial = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    protect_tweeter(initial)
    encoded = (tmp_path / "current.json").read_bytes()
    (tmp_path / "protections.json").unlink()  # simulate a state directory predating this feature
    migrated = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    assert (tmp_path / "current.json").read_bytes() == encoded
    assert migrated.protections.outputs["A"].min_hp_hz == 1500


def test_corrupt_or_future_protection_file_fails_closed(engine, synthetic_mapping):
    path = engine.data_dir / "protections.json"
    value = json.loads(path.read_text())
    value["version"] = 2
    path.write_text(json.dumps(value))
    with pytest.raises(ValidationError):
        Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)


def test_removed_equipment_cannot_erase_recorded_limits(engine):
    protect_tweeter(engine)
    driver = equipment.Component(kind=equipment.Kind.SPEAKER, channels=["A"], specs={
        "fs": equipment.Spec(value=1100), "lp_max": equipment.Spec(value=12000),
        "hp_min_slope": equipment.Spec(value=24),
    })
    engine.design.components.append(driver)
    engine.save_design()
    engine.design.components.remove(driver)
    engine.save_design()
    guard = engine.protections.outputs["A"]
    assert (guard.min_hp_hz, guard.min_hp_slope_db, guard.max_lp_hz) == (2200, 24, 12000)
    with pytest.raises(SafetyRejected):
        engine.edit("test", "too low", lambda t: setattr(t.channel("A"), "hp", Crossover(freq_hz=1800)))


def test_driver_limits_merge_strictest_slope():
    design = equipment.SystemDesign(components=[equipment.Component(
        kind=equipment.Kind.SPEAKER, channels=["A"], specs={"hp_min": equipment.Spec(value=1000),
        "hp_min_slope": equipment.Spec(value=slope)}) for slope in (12, 24)])
    assert equipment.channel_driver_limits(design)["A"].hp_min_slope == 24


def test_explicit_reconfiguration_requires_confirmation_and_disconnect(engine):
    protect_tweeter(engine)
    engine.edit("test", "relabel after equipment change", lambda t: setattr(t.channel("A"), "role", Role.UNUSED))
    empty = safety.OutputProtection()
    with pytest.raises(EngineError, match="RECONFIGURE"):
        engine.configure_output_protection("A", empty, "yes")
    engine.attach(Client(EmulatedDevice()), "emulator")
    with pytest.raises(EngineError, match="disconnect"):
        engine.configure_output_protection("A", empty, "RECONFIGURE")
    engine.detach()
    engine.configure_output_protection("A", empty, "RECONFIGURE")
    engine.edit("test", "remove old crossover", lambda t: setattr(t.channel("A"), "hp", None))
    assert engine.protections.outputs["A"].min_hp_hz is None


def test_reconfiguration_cannot_override_current_driver_role(engine):
    protect_tweeter(engine)
    result = engine.configure_output_protection("A", safety.OutputProtection(), "RECONFIGURE")
    assert result["min_hp_hz"] == 1500


def test_impossible_equipment_limit_does_not_poison_saved_design(engine, synthetic_mapping):
    protect_tweeter(engine)
    before = engine.design.model_dump()
    engine.design.components.append(equipment.Component(kind=equipment.Kind.SPEAKER, channels=["A"],
        specs={"fs": equipment.Spec(value=20000)}))
    with pytest.raises(EngineError, match="Invalid system design"):
        engine.save_design()
    assert engine.design.model_dump() == before
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.protections.outputs["A"].min_hp_hz == 1500
