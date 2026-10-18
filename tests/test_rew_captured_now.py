"""One-step 'captured just now' REW import, bound to a synchronized connection (Codex M7 review)."""
import pytest

from test_rew import UID, api, rew  # noqa: F401  (fixtures)
from helixtune.emulator import EmulatedDevice
from helixtune.equipment import Component, Kind, SystemDesign
from helixtune.protocol.client import Client


def _sync(engine):
    engine.design = SystemDesign(components=[Component(id="mb-l", kind=Kind.SPEAKER, make="Maker", model="Mid 6",
                                                       channels=["A"])])
    engine.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), "emulator")
    engine.push_full("OVERWRITE")


def _body(c, engine, **over):
    fp = c.get(f"/api/rew/measurements/{UID}").json()["fingerprint"]
    body = {"uuid": UID, "expected_fingerprint": fp, "channels": ["A"], "seat": "driver", "captured_now": True,
            "owner_confirmed": True, "expected_revision": engine.revision,
            "expected_connection_epoch": engine._connection_epoch}
    return body | over


def test_captured_now_records_the_synchronized_tune_and_current_drivers(api):
    engine, _, client = api
    with client as c:
        _sync(engine)
        r = c.post("/api/rew/import", json=_body(c, engine))
        assert r.status_code == 200, r.text
        m = engine.measurements.get(r.json()["id"])
        assert m.tune == engine.tune and m.drivers == {"A": [{"id": "mb-l", "make": "Maker", "model": "Mid 6"}]}
        assert engine.measurement_status(m) == ("current", "")
        ctx = m.import_provenance["capture_context"]
        assert ctx["kind"] == "captured_now" and "no hardware readback" in ctx["limits"]
        assert m.driver_history[-1].reason.startswith("Captured just now")
    engine.detach()


@pytest.mark.parametrize("over, code", [
    ({"owner_confirmed": False}, 422),
    ({"tune_snapshot": "Some scene"}, 422),
    ({"channels": []}, 422),
    ({"expected_revision": -1}, 409),
    ({"expected_connection_epoch": -1}, 409),
    ({"channels": ["B"]}, 409),                 # no drivers recorded on B
])
def test_captured_now_refusals_create_nothing(api, over, code):
    engine, _, client = api
    with client as c:
        _sync(engine)
        before = len(engine.measurements.list())
        r = c.post("/api/rew/import", json=_body(c, engine, **over))
        assert r.status_code == code, r.text
        assert len(engine.measurements.list()) == before
    engine.detach()


def test_captured_now_needs_a_synchronized_connection(api):
    engine, _, client = api
    with client as c:
        r = c.post("/api/rew/import", json=_body(c, engine))                        # offline
        assert r.status_code == 409 and "synchronized" in r.text
        engine.design = SystemDesign(components=[Component(id="mb-l", kind=Kind.SPEAKER, make="M", model="X", channels=["A"])])
        engine.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), "emulator")   # connected, not synced
        assert c.post("/api/rew/import", json=_body(c, engine)).status_code == 409
    engine.detach()


def test_seat_spelling_is_normalised_on_import_and_selection(api):
    engine, _, client = api
    with client as c:
        fp = c.get(f"/api/rew/measurements/{UID}").json()["fingerprint"]
        r = c.post("/api/rew/import", json={"uuid": UID, "expected_fingerprint": fp, "channels": ["A"], "seat": "  Driver "})
        m = engine.measurements.get(r.json()["id"])
        assert m.seat == "driver"
        legacy = m.model_copy(update={"id": "legacy0001"})
        object.__setattr__(legacy, "seat", "Passenger")                          # stored before normalisation
        engine.measurements.save(legacy)
        _, excluded, available = engine._prediction_selection("PASSENGER")
        assert available == 1


def test_repeated_import_with_differently_spelled_seat_is_deduplicated(api):
    """Codex review of c17786f: dedupe compared the raw seat, so '  Driver ' imported twice made two records."""
    engine, _, client = api
    with client as c:
        fp = c.get(f"/api/rew/measurements/{UID}").json()["fingerprint"]
        body = {"uuid": UID, "expected_fingerprint": fp, "channels": ["A"]}
        first = c.post("/api/rew/import", json=body | {"seat": "  Driver "}).json()
        for seat in ("  Driver ", "DRIVER", "driver"):
            again = c.post("/api/rew/import", json=body | {"seat": seat}).json()
            assert again == {"id": first["id"], "created": False}
        assert c.post("/api/rew/import", json=body | {"seat": "   "}).status_code == 422
        assert len(engine.measurements.list()) == 1
