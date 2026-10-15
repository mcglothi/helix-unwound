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
    assert owner.post(f"/api/measurements/{engine._mid}/attest").status_code == 200
    pid = agent.post("/api/propose/auto-eq", json={"channels": ["C"]}).json()["id"]
    agent.patch("/api/channels/C/eq/1", json={"enabled": True, "gain_db": -1})
    r = agent.post(f"/api/proposals/{pid}/apply")
    assert r.status_code == 409 and r.json()["error"] == "conflict" and r.json()["conflicts"]
    assert agent.get(f"/api/proposals/{pid}/preview").status_code == 409
    assert agent.get(f"/api/proposals/{pid}").status_code == 200
