import pytest
from conftest import owner_client

from helixtune.api import create_app
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError, SafetyRejected
from helixtune.model import Role
from helixtune.protocol import commands, frame
from helixtune.protocol.client import Client


class FaultDevice(EmulatedDevice):
    """Lose a reply after the write landed, or fail before sending it."""

    fail_on = None
    writes = 0
    lose_reply = True

    def write(self, data):
        if bytes(data) == frame.SYNC_FRAME:      # session baud-change burst, not a frame
            return super().write(data)
        req, _ = frame.decode_tx(data)
        if req.payload[0] == commands.Cmd.WRITE_RAM:
            self.writes += 1
            if self.writes == self.fail_on:
                if not self.lose_reply:
                    raise OSError("injected transport failure")
                result = super().write(data)
                self._out.clear()
                return result
        return super().write(data)


@pytest.fixture
def engine(tmp_path, synthetic_mapping):
    return Engine(mapping=synthetic_mapping, data_dir=tmp_path)


def connect(engine, *, baseline=True):
    dev = FaultDevice()
    engine.attach(Client(dev, allow_writes=True, timeout=0.01), "emulator")
    if baseline:
        engine.push_full("OVERWRITE")
    dev.writes = 0
    return dev


def change_two_outputs(tune):
    tune.channel("A").gain_db = -5
    tune.channel("J").gain_db = -5


def assert_image_matches(engine, dev):
    assert engine.applied_image is not None
    assert all(bytes(dev.ram[a * 4:a * 4 + 4]) == word for a, word in engine.applied_image.items())


@pytest.mark.parametrize("fail_on", [1, 2])
@pytest.mark.parametrize("lose_reply", [False, True])
def test_interrupted_edit_invalidates_baseline_and_preserves_accepted_tune(engine, fail_on, lose_reply):
    dev = connect(engine)
    saved = (engine.data_dir / "current.json")
    engine.edit("test", "persist accepted tune", lambda t: setattr(t, "name", "accepted"))
    previous = engine.tune.model_dump()
    persisted = saved.read_bytes()
    history = len(engine.history)
    dev.writes = 0
    dev.fail_on, dev.lose_reply = fail_on, lose_reply
    with pytest.raises(EngineError, match="device state is unknown"):
        engine.edit("test", "interrupted", change_two_outputs)
    assert engine.tune.model_dump() == previous
    assert saved.read_bytes() == persisted
    assert len(engine.history) == history
    assert engine.device.baselined is False
    assert engine.device.sync_state == "uncertain"
    assert engine.applied_image is None
    assert engine.pending_writes > 0

    # Edits may be staged offline, but never resume incremental writes silently.
    writes = dev.writes
    result = engine.edit("test", "stage offline", lambda t: setattr(t.channel("B"), "gain_db", -8))
    assert result["writes"] == 0 and result["live"] is False
    assert dev.writes == writes
    assert engine.device.sync_state == "uncertain"
    with pytest.raises(EngineError):
        engine.push_full("yes")
    assert dev.writes == writes
    dev.fail_on = None
    engine.push_full("OVERWRITE")
    assert engine.device.baselined is True
    assert engine.device.sync_state == "synchronized"
    assert engine.device.last_error is None
    assert engine.pending_writes == 0
    assert_image_matches(engine, dev)


@pytest.mark.parametrize("baseline", [False, True])
def test_failed_full_push_and_failed_recovery_stay_uncertain(engine, baseline):
    dev = connect(engine, baseline=baseline)
    assert engine.device.sync_state == ("synchronized" if baseline else "unsynchronized")
    for _ in range(2):
        dev.writes = 0
        dev.fail_on = 2
        with pytest.raises(EngineError):
            engine.push_full("OVERWRITE")
        assert engine.device.sync_state == "uncertain"
        assert engine.device.baselined is False
        assert engine.applied_image is None
    dev.fail_on = None
    engine.push_full("OVERWRITE")
    assert_image_matches(engine, dev)
    engine.detach()
    assert engine.device.sync_state == "disconnected"
    connect(engine, baseline=False)
    assert engine.device.baselined is False
    assert engine.device.sync_state == "unsynchronized"


def test_full_push_rechecks_policy_before_any_write(engine):
    dev = connect(engine, baseline=False)
    engine.tune.channel("A").role = Role.TWEETER  # unsafe state loaded or changed out of band
    with pytest.raises(SafetyRejected, match="high-pass filter required"):
        engine.push_full("OVERWRITE")
    assert dev.writes == 0
    assert engine.device.sync_state == "unsynchronized"


def test_full_push_revalidates_mutated_model_before_any_write(engine):
    dev = connect(engine, baseline=False)
    engine.tune.channels[-1].id = "A"
    with pytest.raises(ValueError):
        engine.push_full("OVERWRITE")
    assert dev.writes == 0


@pytest.mark.parametrize("operation", ["undo", "snapshot", "ab"])
def test_failed_restore_preserves_history_and_ab_slots(engine, operation):
    dev = connect(engine)
    engine.save_snapshot("original")
    engine.ab_set("A", None)
    engine.ab_set("B", "original")
    engine.edit("test", "accepted changes", change_two_outputs)
    tune = engine.tune.model_dump()
    history = [t.model_dump() for t in engine.history]
    ab = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in engine.ab.items()}
    dev.writes = 0
    dev.fail_on = 2
    with pytest.raises(EngineError):
        if operation == "undo":
            engine.undo()
        elif operation == "snapshot":
            engine.load_snapshot("original", "test")
        else:
            engine.ab_toggle("test")
    assert engine.tune.model_dump() == tune
    assert [t.model_dump() for t in engine.history] == history
    assert engine.redo_stack == []
    assert {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in engine.ab.items()} == ab
    assert engine.device.sync_state == "uncertain"


def test_api_reports_write_failure_and_allows_explicit_recovery(engine):
    dev = connect(engine)
    api = owner_client(create_app(engine))
    dev.fail_on = 1
    response = api.patch("/api/channels/A", json={"gain_db": -5})
    assert response.status_code == 400
    assert "device state is unknown" in response.json()["detail"]
    state = api.get("/api/status").json()["device"]
    assert state["sync_state"] == "uncertain"
    assert state["baselined"] is False
    assert state["last_error"]
    dev.fail_on = None
    assert api.post("/api/device/push-full", json={"confirm": "OVERWRITE"}).status_code == 200
    assert api.get("/api/status").json()["device"]["sync_state"] == "synchronized"


def test_api_rejects_duplicate_outputs_before_writing(engine):
    dev = connect(engine)
    api = owner_client(create_app(engine))
    data = engine.tune.model_dump(mode="json")
    data["channels"][-1]["id"] = "A"
    assert api.put("/api/tune", json=data).status_code == 422
    assert dev.writes == 0
