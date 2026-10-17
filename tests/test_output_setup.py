import pytest
from fastapi.testclient import TestClient

from conftest import owner_client
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.emulator import EmulatedDevice
from helixtune.protocol.client import Client
from test_device_state import connect


@pytest.fixture
def api(tmp_path, synthetic_mapping):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    app = create_app(engine)
    with owner_client(app) as owner:
        yield engine, app, owner


def draft(owner, cid='A', **changes):
    review = owner.get(f'/api/outputs/{cid}/setup').json()
    channel = review['channel']
    return {'name': channel['name'], 'role': channel['role'], 'mix': channel['mix'],
            'expected_context': review['context'], **changes}


def test_output_setup_is_single_undoable_change_and_survives_restart(api):
    engine, _, owner = api
    before = engine.tune.channel('A').model_dump()
    body = draft(owner, name='Door left', mix={'R': 0.5, 'L': 0.25})
    assert owner.put('/api/outputs/A/setup', json=body).status_code == 200
    assert engine.tune.channel('A').mix == {'R': 0.5, 'L': 0.25}
    assert len(engine.history) == 1
    again = Engine(mapping=engine.mapping, data_dir=engine.data_dir)
    assert again.tune.channel('A').name == 'Door left'
    engine.undo()
    assert engine.tune.channel('A').model_dump() == before


@pytest.mark.parametrize('change', ['channel', 'connection', 'equipment', 'policy', 'restart'])
def test_changed_context_refused_without_altering_state(api, change):
    engine, app, owner = api
    body = draft(owner, name='Draft')
    if change == 'channel': engine.edit('test', 'new gain', lambda t: setattr(t.channel('A'), 'gain_db', -1))
    elif change == 'connection': engine.attach(Client(EmulatedDevice()), 'emulator')
    elif change == 'equipment': engine.design.components[0].name = 'Updated equipment'
    elif change == 'policy': engine.policy.max_channel_gain_db = 5
    else:
        replacement = Engine(mapping=engine.mapping, data_dir=engine.data_dir)
        # Same authenticated HTTP path, new engine/server boot context.
        with owner_client(create_app(replacement)) as new_owner:
            assert new_owner.put('/api/outputs/A/setup', json=body).status_code == 409
        return
    before = engine.tune.model_dump()
    response = owner.put('/api/outputs/A/setup', json=body)
    assert response.status_code == 409
    assert engine.tune.model_dump() == before


def test_role_change_does_not_bypass_high_pass_rules(api):
    engine, _, owner = api
    body = draft(owner, role='tweeter')
    before = engine.tune.model_dump()
    response = owner.put('/api/outputs/A/setup', json=body)
    assert response.status_code == 409 and 'high-pass' in str(response.json())
    assert engine.tune.model_dump() == before and not engine.history


def test_unrelated_output_change_is_mergeable(api):
    engine, _, owner = api
    body = draft(owner, name='Door left')
    engine.edit('test', 'other output', lambda t: setattr(t.channel('B'), 'gain_db', -1))
    assert owner.put('/api/outputs/A/setup', json=body).status_code == 200
    assert engine.tune.channel('B').gain_db == -1


def test_live_route_change_and_failed_write_keep_existing_recovery_semantics(api):
    engine, _, owner = api
    device = connect(engine)
    review = owner.get('/api/outputs/A/setup').json()
    assert review['live']
    body = draft(owner, mix={'R': 1})
    assert owner.put('/api/outputs/A/setup', json=body).status_code == 200
    accepted = engine.tune.model_dump()
    body = draft(owner, mix={'L': 1})
    device.writes = 0
    device.fail_on = 1
    assert owner.put('/api/outputs/A/setup', json=body).status_code == 400
    assert engine.tune.model_dump() == accepted
    assert engine.device.sync_state == 'uncertain'


def test_agent_cannot_apply_output_setup_and_anonymous_cannot_read(api):
    engine, app, owner = api
    body = draft(owner, name='Owner only')
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/outputs/A/setup').status_code == 401
    with TestClient(app, headers={'Authorization': f'Bearer {app.state.access.token("agent")}'}) as agent:
        assert agent.put('/api/outputs/A/setup', json=body).status_code == 403
    assert engine.tune.channel('A').name != 'Owner only'


@pytest.mark.parametrize('mix', [{'unexpected': 1}, {'L': -1}, {'R': 2}])
def test_invalid_input_mix_returns_useful_validation_error_without_changing_tune(api, mix):
    engine, _, owner = api
    before = engine.tune.model_dump()
    response = owner.put('/api/outputs/A/setup', json=draft(owner, mix=mix))
    assert response.status_code == 422
    assert response.json()['detail'][0]['msg']
    assert engine.tune.model_dump() == before and not engine.history


def test_turning_last_input_off_stays_off_after_validation_save_and_restart(api):
    engine, _, owner = api
    for channel in engine.tune.channels:
        channel.mix = {}
    engine.tune.channel('A').mix = {'L': 1}
    assert owner.put('/api/outputs/A/setup', json=draft(owner, mix={})).status_code == 200
    assert all(channel.mix == {} for channel in engine.tune.channels)
    again = Engine(mapping=engine.mapping, data_dir=engine.data_dir)
    assert all(channel.mix == {} for channel in again.tune.channels)
    again.undo()
    assert again.tune.channel('A').mix == {'L': 1}
    assert all(channel.mix == {} for channel in again.tune.channels[1:])


def test_legacy_routing_migration_uses_physical_ids_and_does_not_mutate_input():
    from helixtune.model import Tune
    raw = Tune().model_dump()
    raw['channels'].reverse()
    for channel in raw['channels']:
        del channel['mix']
    restored = Tune.model_validate(raw)
    assert restored.channel('A').mix == {'L': 1} and restored.channel('J').mix == {'R': 1}
    assert all('mix' not in channel for channel in raw['channels'])
