import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import owner_client
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.equipment import Component, Kind
from helixtune.measurements import GRID, Measurement
from helixtune.model import Crossover, Role


@pytest.fixture
def capture(tmp_path, synthetic_mapping):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    def configure(t):
        ch = t.channel("A")
        ch.hp, ch.lp, ch.role = Crossover(freq_hz=60), Crossover(freq_hz=3000), Role.MIDBASS
    engine.edit("test", "configure current driver", configure)
    engine.design.components.append(Component(id="door-left", kind=Kind.SPEAKER,
        make="Audiofrog", model="GS690", channels=["A"]))
    engine.save_design()
    spl = 80 + 7 * np.exp(-np.log2(GRID / 400) ** 2 / 0.08)
    measurement = Measurement(name="2018 left midbass", channels=["A"], taken_at=1517097600,
        freqs=GRID.tolist(), spl=spl.tolist(), tune=engine.tune.model_copy(deep=True))
    engine.measurements.save(measurement)
    app = create_app(engine)
    return engine, measurement, owner_client(app), TestClient(app,
        headers={"Authorization": f"Bearer {app.state.access.token('agent')}"})


def body(engine, measurement, *, historical=False):
    return {"drivers": {"A": [{"id": "historical:2018-left", "make": "Audiofrog", "model": "GB60"}]} if historical else
            {"A": engine.driver_identity("A")}, "reason": "Installation notes identify capture-time drivers",
            "expected_fingerprint": engine.measurement_metadata(measurement.id)["capture_fingerprint"]}


def test_http_requires_explicit_capture_record_and_owner_authority(capture):
    engine, measurement, owner, agent = capture
    path = f"/api/measurements/{measurement.id}/attest"
    assert owner.post(path).status_code == 422
    assert agent.post(path, json=body(engine, measurement)).status_code == 403
    assert engine.measurements.get(measurement.id).drivers is None


def test_historical_gb60_never_inherits_current_gs690_identity(capture, synthetic_mapping):
    engine, measurement, owner, _ = capture
    raw_before = engine.measurements.get(measurement.id)
    response = owner.post(f"/api/measurements/{measurement.id}/attest", json=body(engine, measurement, historical=True))
    assert response.status_code == 200
    record = response.json()
    assert record["status"] == "stale" and record["optimizable"] is False
    assert record["drivers"]["A"][0]["model"] == "GB60"
    assert record["current_drivers"]["A"][0]["model"] == "GS690"
    assert record["driver_history"][0]["action"] == "attest"
    after = engine.measurements.get(measurement.id)
    assert after.spl == raw_before.spl and after.tune == raw_before.tune
    assert engine.design.get("door-left").model == "GS690"
    assert engine.propose_auto_eq(["A"])["edits"] == []
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.measurement_metadata(measurement.id)["drivers"]["A"][0]["model"] == "GB60"


def test_current_record_is_explicit_and_metadata_excludes_raw_arrays(capture):
    engine, measurement, owner, _ = capture
    response = owner.post(f"/api/measurements/{measurement.id}/attest", json=body(engine, measurement))
    assert response.status_code == 200 and response.json()["optimizable"] is True
    assert "spl" not in response.json() and "freqs" not in response.json() and "tune" not in response.json()
    assert owner.get("/api/measurements").json()[0]["status"] == "current"
    assert engine.propose_auto_eq(["A"])["edits"]


def test_stale_review_cannot_overwrite_changed_capture(capture):
    engine, measurement, owner, _ = capture
    pending = body(engine, measurement)
    owner.patch(f"/api/measurements/{measurement.id}", json={"seat": "passenger"})
    response = owner.post(f"/api/measurements/{measurement.id}/attest", json=pending)
    assert response.status_code == 409 and response.json()["error"] == "measurement_conflict"
    assert engine.measurements.get(measurement.id).drivers is None


def test_correcting_record_requires_explicit_flag_and_preserves_previous_record(capture):
    engine, measurement, owner, _ = capture
    path = f"/api/measurements/{measurement.id}/attest"
    owner.post(path, json=body(engine, measurement, historical=True))
    pending = body(engine, measurement, historical=True)
    pending["drivers"]["A"][0]["model"] = "GB60 corrected label"
    persisted = engine.measurements.get(measurement.id).model_dump()
    assert owner.post(path, json=pending).status_code == 409
    assert engine.measurements.get(measurement.id).model_dump() == persisted
    pending.update(correct_existing=True, reason="Original capture note had an incomplete model label")
    response = owner.post(path, json=pending)
    assert response.status_code == 200 and response.json()["status"] == "stale"
    history = response.json()["driver_history"]
    assert len(history) == 2 and history[-1]["action"] == "correct"
    assert history[-1]["previous_drivers"]["A"][0]["model"] == "GB60"


@pytest.mark.parametrize("change", [{"channels": ["B"]}, {"seat": "passenger"}, {"clear_tune": True}])
def test_capture_context_changes_invalidate_confirmation_and_retain_history(capture, change):
    engine, measurement, owner, agent = capture
    owner.post(f"/api/measurements/{measurement.id}/attest", json=body(engine, measurement))
    response = agent.patch(f"/api/measurements/{measurement.id}", json=change)
    assert response.status_code == 200
    record = response.json()
    assert record["drivers"] is None and record["optimizable"] is False
    assert record["driver_history"][-1]["action"] == "invalidate"
    assert record["driver_history"][-1]["source"] == "agent"
    assert record["driver_history"][-1]["previous_drivers"]["A"][0]["model"] == "GS690"


def test_presentation_edits_do_not_clear_confirmation(capture):
    engine, measurement, owner, _ = capture
    owner.post(f"/api/measurements/{measurement.id}/attest", json=body(engine, measurement))
    response = owner.patch(f"/api/measurements/{measurement.id}", json={"name": "Left door", "notes": "Review complete"})
    assert response.status_code == 200 and response.json()["status"] == "current"
    assert len(response.json()["driver_history"]) == 1


@pytest.mark.parametrize("invalid", ["missing_channel", "empty_drivers", "blank_reason", "blank_model", "duplicate_ids"])
def test_incomplete_evidence_is_rejected_without_changing_measurement(capture, invalid):
    engine, measurement, owner, _ = capture
    pending = body(engine, measurement)
    if invalid == "missing_channel": pending["drivers"] = {}
    elif invalid == "empty_drivers": pending["drivers"]["A"] = []
    elif invalid == "blank_reason": pending["reason"] = " " * 15
    elif invalid == "blank_model": pending["drivers"]["A"][0]["model"] = " "
    else: pending["drivers"]["A"] *= 2
    response = owner.post(f"/api/measurements/{measurement.id}/attest", json=pending)
    assert response.status_code in (400, 422)
    assert engine.measurements.get(measurement.id).drivers is None


def test_known_hardware_without_capture_tune_is_not_a_level_anchor(capture):
    engine, measurement, owner, _ = capture
    owner.patch(f"/api/measurements/{measurement.id}", json={"clear_tune": True})
    record = owner.post(f"/api/measurements/{measurement.id}/attest", json=body(engine, measurement)).json()
    assert record["status"] == "current" and record["optimizable"] is False
    assert engine._anchor_measurements("driver") == []
    assert any("no trusted measurement" in note for note in engine.propose_levels()["notes"])


def test_clear_tune_and_snapshot_cannot_be_requested_together(capture):
    _, measurement, owner, _ = capture
    response = owner.patch(f"/api/measurements/{measurement.id}", json={"clear_tune": True, "tune_snapshot": "anything"})
    assert response.status_code == 400
