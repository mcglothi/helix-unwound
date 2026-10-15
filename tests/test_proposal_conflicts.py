"""Proposal binding: field before-values + measurement/target/driver context. Synthetic only."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import owner_client
from helixtune import equipment as eq
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.measurements import GRID, Measurement
from helixtune.model import Crossover, Role
from helixtune.proposals import ProposalConflict


@pytest.fixture
def engine(tmp_path, synthetic_mapping):
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)

    def setup(t):
        ch = t.channel("C")
        ch.role, ch.name = Role.MIDRANGE, "Mid L"
        ch.hp = Crossover(freq_hz=300)
        ch.lp = Crossover(freq_hz=3000)
    e.edit("test", "setup", setup)
    e.design = eq.SystemDesign(components=[eq.Component(kind=eq.Kind.SPEAKER, name="Mid L", make="Audiofrog",
                                                        model="GB25", channels=["C"])])
    e.save_design()
    # synthetic measurement: target-shaped response with a +7 dB bump at 500 Hz, tied to this tune
    spl = 80 + 7 * np.exp(-np.log2(GRID / 500) ** 2 / 0.08)
    m = Measurement(name="mid", channels=["C"], freqs=GRID.tolist(), spl=spl.tolist(), tune=e.tune.model_copy(deep=True))
    e.measurements.save(m)
    e._mid = m.id
    return e


def test_legacy_measurement_refused_until_attested(engine):
    p = engine.propose_auto_eq(["C"])
    assert p["edits"] == [] and any("unknown" in n for n in p["notes"])
    engine.attest_measurement(engine._mid, "owner")
    assert engine.propose_auto_eq(["C"])["edits"]


def test_replaced_driver_makes_measurement_stale(engine):
    engine.attest_measurement(engine._mid, "owner")
    comp = engine.design.components[0]
    engine.design.components[0] = comp.model_copy(update={"model": "GS25"})
    engine.save_design()
    p = engine.propose_auto_eq(["C"])
    assert p["edits"] == [] and any("now Audiofrog GS25" in n for n in p["notes"])


def _ready(engine):
    engine.attest_measurement(engine._mid, "owner")
    return engine.propose_auto_eq(["C"])["id"]


def test_unrelated_edit_still_merges(engine):
    pid = _ready(engine)
    engine.edit("test", "other channel", lambda t: setattr(t.channel("A"), "gain_db", -3))
    engine.apply_proposal(pid, "test")
    assert any(b.enabled for b in engine.tune.channel("C").eq)
    assert engine.tune.channel("A").gain_db == -3


@pytest.mark.parametrize("change", ["field", "target", "measurement", "driver"])
def test_conflicts_leave_state_and_proposal_intact(engine, change):
    pid = _ready(engine)
    if change == "field":
        engine.edit("test", "manual EQ", lambda t: setattr(t.channel("C").eq[0], "enabled", True))
    elif change == "target":
        engine.target_name = "Flat"
    elif change == "measurement":
        m = engine.measurements.get(engine._mid)
        engine.measurements.save(m.model_copy(update={"spl": [v + 1 for v in m.spl]}))
    else:
        c = engine.design.components[0]
        engine.design.components[0] = c.model_copy(update={"make": "Other"})
        engine.save_design()
    before = engine.tune.model_copy(deep=True)
    with pytest.raises(ProposalConflict):
        engine.preview_proposal(pid)
    with pytest.raises(ProposalConflict):
        engine.apply_proposal(pid, "test")
    assert engine.tune == before
    assert pid in engine.proposals


def test_harmless_revision_bump_is_not_a_conflict(engine):
    pid = _ready(engine)
    engine.revision += 5  # e.g. theme / layout / media changes
    engine.apply_proposal(pid, "test")


def test_conflict_over_http_and_attest_is_owner_only(engine):
    app = create_app(engine)
    owner = owner_client(app)
    agent = TestClient(app, headers={"Authorization": f"Bearer {app.state.access.token('agent')}"})
    assert agent.post(f"/api/measurements/{engine._mid}/attest").status_code == 403
    metadata = owner.get(f"/api/measurements/{engine._mid}").json()
    assert owner.post(f"/api/measurements/{engine._mid}/attest", json={
        "drivers": metadata["current_drivers"], "reason": "Synthetic fixture has known capture hardware",
        "expected_fingerprint": metadata["capture_fingerprint"]}).status_code == 200
    pid = agent.post("/api/propose/auto-eq", json={"channels": ["C"]}).json()["id"]
    agent.patch("/api/channels/C/eq/1", json={"enabled": True, "gain_db": -1})
    r = agent.post(f"/api/proposals/{pid}/apply")
    assert r.status_code == 409 and r.json()["error"] == "conflict" and r.json()["conflicts"]
    assert agent.get(f"/api/proposals/{pid}/preview").status_code == 409
    assert agent.get(f"/api/proposals/{pid}").status_code == 200


# ---- solver inputs, not just destinations (review of 39aed64) ---------------------------

def test_crossover_change_after_eq_fit_conflicts(engine):
    pid = _ready(engine)
    engine.edit("test", "move HP", lambda t: setattr(t.channel("C").hp, "freq_hz", 700))
    assert engine.proposal_conflicts(engine.proposals[pid])


def test_eq_or_crossover_change_after_levels_conflicts(engine):
    engine.attest_measurement(engine._mid, "owner")
    for change in ("eq", "lp"):
        pid = engine.propose_levels()["id"]
        if change == "eq":
            engine.edit("test", "eq", lambda t: (setattr(t.channel("C").eq[3], "enabled", True),
                                                 setattr(t.channel("C").eq[3], "gain_db", -2)))
        else:
            engine.edit("test", "lp", lambda t: setattr(t.channel("C").lp, "freq_hz", 2500))
        assert engine.proposal_conflicts(engine.proposals[pid]), change


def test_driver_reassignment_after_alignment_conflicts(engine):
    pid = engine.propose_alignment({"C": 120, "A": 150})["id"]
    c = engine.design.components[0]
    engine.design.components[0] = c.model_copy(update={"channels": ["D"]})
    engine.save_design()
    assert engine.proposal_conflicts(engine.proposals[pid])


def test_unrelated_presentation_edit_still_merges_with_levels(engine):
    engine.attest_measurement(engine._mid, "owner")
    pid = engine.propose_levels()["id"]
    engine.edit("test", "rename", lambda t: setattr(t.channel("C"), "name", "Mid Left"))
    engine.edit("test", "other channel", lambda t: setattr(t.channel("A"), "gain_db", -2))
    assert engine.proposal_conflicts(engine.proposals[pid]) == []


# ---- solver target provenance -----------------------------------------------------------

def _loud_unknown(engine, channel="A", level=120.0):
    m = Measurement(name="old loud", channels=[channel], freqs=GRID.tolist(), spl=[level] * len(GRID),
                    tune=engine.tune.model_copy(deep=True))
    engine.measurements.save(m)
    return m


def test_untrusted_measurements_cannot_move_solver_targets(engine):
    engine.attest_measurement(engine._mid, "owner")
    engine.edit("test", "offset", lambda t: setattr(t.channel("C"), "gain_db", -4))  # give levels work to do
    pid = engine.propose_levels()["id"]
    first = engine.proposals[pid]
    _loud_unknown(engine)  # unknown provenance, 40 dB hotter
    assert engine.proposal_conflicts(first) == []
    again = engine.proposals[engine.propose_levels()["id"]]
    assert again.context.target == first.context.target
    assert [(e.channel, e.value) for e in again.edits] == [(e.channel, e.value) for e in first.edits]


def test_meaningful_contributor_change_conflicts(engine):
    engine.attest_measurement(engine._mid, "owner")
    pid = engine.propose_levels()["id"]
    # a newer trusted measurement of the same contributor changes the level anchor
    m = engine.measurements.get(engine._mid)
    newer = m.model_copy(update={"id": "newer", "spl": [v + 6 for v in m.spl], "taken_at": m.taken_at + 60})
    engine.measurements.save(newer)
    assert engine.proposal_conflicts(engine.proposals[pid])


def test_levels_refused_without_trusted_anchor(engine):
    p = engine.propose_levels()  # only an unknown-provenance measurement exists
    assert p["edits"] == [] and any("trusted" in n for n in p["notes"])
