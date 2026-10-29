"""Restart/recovery and accepted-write semantics, entirely synthetic."""
import json

import pytest

from conftest import owner_client
from helixtune import workstation
from helixtune.api import create_app
from helixtune.engine import Engine, EngineError, SafetyRejected
from test_device_state import connect


@pytest.fixture
def engine(tmp_path, synthetic_mapping):
    return Engine(mapping=synthetic_mapping, data_dir=tmp_path)


def restart(engine):
    return Engine(mapping=engine.mapping, data_dir=engine.data_dir)


def edit(engine, gain):
    return engine.edit('test', f'gain {gain}', lambda t: setattr(t.channel('A'), 'gain_db', gain))


def test_restart_restores_history_redo_slots_but_no_hardware_state(engine):
    edit(engine, -1)
    engine.ab_set('A', None)
    edit(engine, -2)
    engine.ab_set('B', None)
    engine.undo()
    connect(engine)
    again = restart(engine)
    assert again.tune.channel('A').gain_db == -1
    assert len(again.history) == 1 and len(again.redo_stack) == 1
    assert again.ab['B'].channel('A').gain_db == -2
    assert again.client is None and again.applied_image is None
    assert again.device.sync_state == 'disconnected' and not again.device.writes_enabled
    again.redo()
    assert again.tune.channel('A').gain_db == -2
    restart(again).undo()


def test_new_edit_and_scene_load_discard_redo_and_survive_restart(engine):
    edit(engine, -1)
    engine.save_snapshot('quieter')
    edit(engine, -2)
    engine.undo()
    assert engine.redo_stack
    engine.load_snapshot('quieter', 'test')
    assert not restart(engine).redo_stack
    engine.undo()
    edit(engine, -3)
    assert not restart(engine).redo_stack


def test_ab_switch_checkpoint_has_final_slots_and_history(engine):
    edit(engine, -1)
    engine.ab_set('A', None)
    edit(engine, -2)
    engine.ab_set('B', None)
    edit(engine, -3)
    engine.ab_toggle('test')
    again = restart(engine)
    assert again.ab['active'] == 'B'
    assert again.tune.channel('A').gain_db == -2
    assert again.ab['A'].channel('A').gain_db == -3
    again.undo()
    assert again.tune.channel('A').gain_db == -3


def test_corrupt_primary_recovers_previous_and_preserves_good_backup(engine):
    edit(engine, -1)
    edit(engine, -2)
    primary = engine.data_dir / 'workstation.json'
    primary.write_text('{truncated')
    again = restart(engine)
    assert again.tune.channel('A').gain_db == -1
    assert 'Recovered' in again.status()['recovery_notice']
    edit(again, -3)
    primary.write_text('broken again')
    assert restart(again).tune.channel('A').gain_db == -1


def test_all_checkpoints_corrupt_never_substitutes_default_or_stale_export(engine):
    edit(engine, -1)
    edit(engine, -2)
    for name in ['workstation.json', 'workstation.previous.json']:
        (engine.data_dir / name).write_text('corrupt')
    with pytest.raises(EngineError, match='no default tune was substituted'):
        restart(engine)


def test_future_version_refused_without_downgrading_to_backup(engine):
    edit(engine, -1)
    edit(engine, -2)
    (engine.data_dir / 'workstation.json').write_text(json.dumps({'version': 99}))
    with pytest.raises(EngineError, match='Unsupported workstation version'):
        restart(engine)


def test_legacy_current_migrates_only_on_first_save(engine):
    legacy = engine.tune.model_copy(deep=True)
    legacy.channel('A').gain_db = -4
    (engine.data_dir / 'current.json').write_text(legacy.model_dump_json())
    again = restart(engine)
    assert again.tune.channel('A').gain_db == -4
    assert not (engine.data_dir / 'workstation.json').exists()
    edit(again, -5)
    assert restart(again).history[-1].channel('A').gain_db == -4


def test_disk_failure_keeps_accepted_live_tune_and_exposes_retry(engine, monkeypatch):
    connect(engine)
    original = workstation.save
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(workstation, 'save', fail)
    result = edit(engine, -1)
    assert result['live'] and engine.tune.channel('A').gain_db == -1
    assert engine.applied_image == engine.mapping.render(engine.tune)
    assert engine.status()['save_error'] and engine.retry_save() == {'ok': False}
    monkeypatch.setattr(workstation, 'save', original)
    assert engine.retry_save() == {'ok': True}
    assert engine.status()['save_error'] is None
    assert restart(engine).tune.channel('A').gain_db == -1


def test_failed_device_redo_preserves_memory_and_checkpoint(engine):
    edit(engine, -1)
    engine.undo()
    dev = connect(engine)
    before = (engine.data_dir / 'workstation.json').read_bytes()
    dev.fail_on = 1
    with pytest.raises(EngineError, match='device state is unknown'):
        engine.redo()
    assert engine.tune.channel('A').gain_db == 0 and len(engine.redo_stack) == 1
    assert (engine.data_dir / 'workstation.json').read_bytes() == before


def test_redo_rechecks_current_protections(engine):
    edit(engine, -1)
    engine.undo()
    engine.policy.max_channel_gain_db = -2
    with pytest.raises(SafetyRejected):
        engine.redo()
    assert len(engine.redo_stack) == 1


def test_atomic_replace_failure_leaves_previous_primary_readable(engine, monkeypatch):
    edit(engine, -1)
    original = workstation.os.replace
    def fail_primary(src, dest):
        if dest.name == 'workstation.json': raise OSError('replace denied')
        return original(src, dest)
    monkeypatch.setattr(workstation.os, 'replace', fail_primary)
    edit(engine, -2)
    assert engine.status()['save_error']
    assert restart(engine).tune.channel('A').gain_db == -1
    assert not list(engine.data_dir.glob('*.tmp'))


def test_redo_and_retry_api_use_owner_auth(engine):
    edit(engine, -1)
    engine.undo()
    with owner_client(create_app(engine)) as client:
        assert client.post('/api/redo').status_code == 200
        assert client.get('/api/status').json()['redo_depth'] == 0
        assert client.post('/api/session/save').json() == {'ok': True}


def test_missing_primary_uses_checkpoint_backup(engine):
    edit(engine, -1)
    edit(engine, -2)
    (engine.data_dir / 'workstation.json').unlink()
    again = restart(engine)
    assert again.tune.channel('A').gain_db == -1 and again.recovery_notice


def test_checkpoint_ignores_manually_changed_compatibility_export(engine):
    edit(engine, -1)
    exported = engine.tune.model_copy(deep=True)
    exported.channel('A').gain_db = -4
    (engine.data_dir / 'current.json').write_text(exported.model_dump_json())
    assert restart(engine).tune.channel('A').gain_db == -1


def test_history_bounded_and_empty_redo_refused(engine):
    with pytest.raises(EngineError, match='nothing to redo'):
        engine.redo()
    # Simulate a full prior session without performing 200 redundant disk writes.
    engine.history = [engine.tune.model_copy(deep=True) for _ in range(200)]
    edit(engine, -1)
    assert len(restart(engine).history) == 200


def test_unwritable_activity_log_does_not_reject_accepted_edit(engine, monkeypatch):
    import builtins
    original = builtins.open
    def fail_log(path, *args, **kwargs):
        if str(path).endswith('events.jsonl'):
            raise OSError('log unavailable')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', fail_log)
    edit(engine, -1)
    assert restart(engine).tune.channel('A').gain_db == -1
    assert 'activity log' in engine.status()['save_error']
    assert engine.retry_save() == {'ok': False}
    monkeypatch.setattr(builtins, 'open', original)
    assert engine.retry_save() == {'ok': True}


def test_runtime_future_file_is_preserved_and_save_failure_visible(engine):
    edit(engine, -1)
    path = engine.data_dir / 'workstation.json'
    future = json.dumps({'version': 99})
    path.write_text(future)
    edit(engine, -2)
    assert engine.tune.channel('A').gain_db == -2 and engine.save_error
    assert path.read_text() == future
