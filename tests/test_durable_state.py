"""Power-loss-safe state (truck computer loses power with the ignition) - M5 review follow-up."""
import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

from conftest import owner_client
from helixtune import durable
from helixtune.api import create_app
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.protocol.client import Client


def test_atomic_write_fsyncs_keeps_permissions_and_survives_a_failed_replace(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("old")
    path.chmod(0o640)
    synced = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd))[1])
    durable.atomic_write(path, "new")
    assert path.read_text() == "new" and len(synced) >= 2                       # file + directory
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("power cut")))
    with pytest.raises(OSError):
        durable.atomic_write(path, "newer")
    assert path.read_text() == "new" and [p.name for p in tmp_path.iterdir()] == ["state.json"]   # no temp left


def test_a_failed_fsync_never_replaces_the_good_file(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("good")
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("I/O error")))
    with pytest.raises(OSError):
        durable.atomic_write(path, "new")
    assert path.read_text() == "good"


def test_backup_keeps_the_previous_good_copy_and_a_damaged_primary_never_overwrites_it(tmp_path):
    path = tmp_path / "x.json"
    durable.write_with_backup(path, '{"v": 1}', valid=json.loads)
    durable.write_with_backup(path, '{"v": 2}', valid=json.loads)
    assert json.loads(durable.backup_path(path).read_text()) == {"v": 1}
    path.write_text('{"v": 3')                                                    # truncated by a power cut
    durable.write_with_backup(path, '{"v": 4}', valid=json.loads)
    assert json.loads(durable.backup_path(path).read_text()) == {"v": 1}


@pytest.fixture
def damaged(synthetic_mapping, tmp_path):
    """An engine whose protections.json was cut off mid-write after at least two saves."""
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    e.tune.channel("C").gain_db = -1.0
    e._persist_protections(e.tune)
    path = tmp_path / "protections.json"
    durable.write_with_backup(path, path.read_text())                            # ensure a backup exists
    good = path.read_text()
    durable.atomic_write(durable.backup_path(path), good)
    path.write_text(good[: len(good) // 2])
    return tmp_path, good


def test_restart_uses_the_backup_keeps_evidence_and_raises_a_fault(synthetic_mapping, damaged):
    data, good = damaged
    e = Engine(mapping=synthetic_mapping, data_dir=data)
    assert e.state_faults and "Output protections" in e.state_faults[0]
    assert e.status()["state_faults"] == e.state_faults and "restored" in e.recovery_notice
    assert e.protection_book.model_dump_json(indent=2) == good
    assert list(data.glob("protections.json.damaged-*"))


def test_every_dsp_write_path_is_blocked_until_the_owner_acknowledges(synthetic_mapping, damaged):
    data, _ = damaged
    e = Engine(mapping=synthetic_mapping, data_dir=data)
    with pytest.raises(EngineError, match="restored from a backup"):
        e.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), "emulator")
    e.attach(Client(EmulatedDevice(), timeout=0.05), "emulator")                  # read-only is fine
    with pytest.raises(EngineError, match="restored from a backup"):
        e.push_full("OVERWRITE")
    e.detach()
    app = create_app(e)
    with TestClient(app, headers={"Authorization": f"Bearer {app.state.access.token('agent')}"}) as agent:
        assert agent.post("/api/state/acknowledge-recovery", json={"reason": "agent says fine"}).status_code == 403
    with owner_client(app) as c:
        r = c.post("/api/device/connect", json={"port": "emulator", "allow_writes": True})
        assert r.status_code >= 400 and "restored from a backup" in r.text
        assert c.post("/api/state/acknowledge-recovery", json={"reason": "short"}).status_code == 422
        assert c.post("/api/state/acknowledge-recovery", json={"reason": "Compared limits with the Setup page"}).status_code == 200
        assert c.get("/api/status").json()["state_faults"] == []
        assert c.post("/api/device/connect", json={"port": "emulator", "allow_writes": True}).status_code == 200
        c.post("/api/device/disconnect")
    assert Engine(mapping=synthetic_mapping, data_dir=data).state_faults == []    # clean after restart


@pytest.mark.parametrize("name, critical", [("system.json", True), ("safety.json", True), ("targets.json", False)])
def test_other_state_files_recover_from_backup(synthetic_mapping, tmp_path, name, critical):
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    if name == "targets.json":
        from helixtune import targets
        e.save_target(targets.Target(name="Mine", points=[[20, 0], [20000, 0]]))
        e.save_target(targets.Target(name="Mine 2", points=[[20, 0], [20000, -3]]))
    path = tmp_path / name
    if not durable.backup_path(path).exists():
        durable.atomic_write(durable.backup_path(path), path.read_text())
    path.write_text(path.read_text()[:10])
    e2 = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    assert bool(e2.state_faults) == critical and e2.recovery_notice


def test_no_usable_copy_refuses_to_start(synthetic_mapping, tmp_path):
    Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    for n in ("system.json", "system.json.bak"):
        if (tmp_path / n).exists():
            (tmp_path / n).write_text("{")
    (tmp_path / "system.json.bak").write_text("{")
    with pytest.raises(EngineError, match="no usable backup"):
        Engine(mapping=synthetic_mapping, data_dir=tmp_path)


# ---- Codex review of 0fb6643 ---------------------------------------------------------------

def _damage_policy_with_good_backup(synthetic_mapping, tmp_path, damaged_text):
    Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    pol = tmp_path / "safety.json"
    good = pol.read_text()
    durable.atomic_write(durable.backup_path(pol), good)
    pol.write_text(damaged_text)
    return pol, good


def test_unacknowledged_fault_survives_restart_and_still_blocks_writes(synthetic_mapping, tmp_path):
    _damage_policy_with_good_backup(synthetic_mapping, tmp_path, '{"roles": ')
    assert Engine(mapping=synthetic_mapping, data_dir=tmp_path).state_faults
    again = Engine(mapping=synthetic_mapping, data_dir=tmp_path)           # restart, no acknowledgement
    assert again.state_faults
    with pytest.raises(EngineError, match="restored from a backup"):
        again.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), "emulator")
    again.acknowledge_recovery("Checked the safety policy values")
    assert Engine(mapping=synthetic_mapping, data_dir=tmp_path).state_faults == []


def test_schema_invalid_policy_never_replaces_the_good_backup(synthetic_mapping, tmp_path):
    raw = json.loads((lambda e: (tmp_path / "safety.json").read_text())(Engine(mapping=synthetic_mapping, data_dir=tmp_path)))
    raw["max_channel_gain_db"] = "broken"
    pol, good = _damage_policy_with_good_backup(synthetic_mapping, tmp_path, json.dumps(raw))
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    assert e.state_faults
    assert durable.backup_path(pol).read_text() == good                       # backup untouched
    assert e.policy.max_channel_gain_db == json.loads(good)["max_channel_gain_db"]


@pytest.mark.parametrize("text", ["[]", '{"version": 2, "constraints": []}', '"text"', "null"])
def test_wrongly_shaped_protections_recover_from_backup(synthetic_mapping, tmp_path, text):
    Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    path = tmp_path / "protections.json"
    durable.atomic_write(durable.backup_path(path), path.read_text())
    path.write_text(text)
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    assert e.state_faults and "Output protections" in e.state_faults[0]


def test_backup_write_failure_propagates_and_leaves_the_primary(tmp_path, monkeypatch):
    path = tmp_path / "x.json"
    durable.write_with_backup(path, '{"v": 1}', valid=json.loads)
    durable.write_with_backup(path, '{"v": 2}', valid=json.loads)
    real = durable.atomic_write

    def failing(p, text):
        if str(p).endswith(".bak"):
            raise OSError("disk full")
        return real(p, text)
    monkeypatch.setattr(durable, "atomic_write", failing)
    with pytest.raises(OSError, match="disk full"):
        durable.write_with_backup(path, '{"v": 3}', valid=json.loads)
    assert json.loads(path.read_text()) == {"v": 2} and json.loads(durable.backup_path(path).read_text()) == {"v": 1}


def test_binary_garbage_primary_recovers_and_saves(synthetic_mapping, tmp_path):
    """Codex review of 012c7a9: a non-UTF-8 primary crashed the first save after recovery."""
    Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    pol = tmp_path / "safety.json"
    good = pol.read_text()
    durable.atomic_write(durable.backup_path(pol), good)
    pol.write_bytes(b"\xff\xfe garbage")
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)                  # must not crash
    assert e.state_faults and durable.backup_path(pol).read_text() == good
