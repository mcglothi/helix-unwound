"""Public hardware-free demo uses invented state and cannot open serial ports."""
import json

import pytest

from conftest import owner_client
from helixtune.api import create_app
from helixtune.cli import main
from helixtune.demo import create_demo_engine, DemoMapping, DEMO_MARKER
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.protocol.client import Client


def test_demo_has_safe_generated_tune_and_eligible_synthetic_captures(tmp_path):
    engine = create_demo_engine(tmp_path)
    assert engine.demo and engine._check(engine.tune) == []
    assert engine.client is None
    assert len(engine.mapping.render(engine.tune)) > 1000
    view = engine.system_view()
    assert view['measurement_count'] == 8
    assert not view['excluded'] and not view['coverage']['missing_outputs']
    assert all(item['state'] == 'pending' for item in engine.protection_view()['constraints'].values())
    for m in engine.measurements.list():
        assert m['name'].startswith('Synthetic') and m['taken_at'] == 0
        assert 'not microphone audio' in m['source']
    assert all(not component.serial for component in engine.design.components)


def test_demo_restart_preserves_edits_and_deleted_fixtures(tmp_path):
    engine = create_demo_engine(tmp_path)
    engine.edit('test', 'change demo tune', lambda t: setattr(t.channel('C'), 'gain_db', -8))
    engine.delete_measurement('demo-A')
    again = create_demo_engine(tmp_path)
    assert again.tune.channel('C').gain_db == -8
    assert len(again.measurements.list()) == 7


def test_demo_refuses_existing_non_demo_state_without_modifying_it(tmp_path):
    path = tmp_path / 'current.json'
    path.write_text('precious existing state')
    with pytest.raises(EngineError, match='empty directory'):
        create_demo_engine(tmp_path)
    assert path.read_text() == 'precious existing state'
    assert not (tmp_path / DEMO_MARKER).exists()


@pytest.mark.parametrize('marker', [{'version': 9, 'seeded': True}, {'version': 1, 'seeded': False}])
def test_incomplete_or_future_demo_data_fails_closed(tmp_path, marker):
    (tmp_path / DEMO_MARKER).write_text(json.dumps(marker))
    with pytest.raises(EngineError, match='Incomplete or unsupported'):
        create_demo_engine(tmp_path)


def test_hardware_engine_cannot_load_demo_state(tmp_path, synthetic_mapping):
    create_demo_engine(tmp_path)
    with pytest.raises(EngineError, match='cannot be opened by a hardware engine'):
        Engine(mapping=synthetic_mapping, data_dir=tmp_path)


def test_demo_api_blocks_physical_ports_before_opening_or_detaching(tmp_path, monkeypatch):
    import serial
    from serial.tools import list_ports
    def forbidden(*args, **kwargs):
        pytest.fail('Demo touched physical serial APIs')
    monkeypatch.setattr(serial, 'Serial', forbidden)
    monkeypatch.setattr(list_ports, 'comports', forbidden)
    engine = create_demo_engine(tmp_path)
    owner = owner_client(create_app(engine))
    assert owner.get('/api/ports').json() == []
    assert owner.get('/api/status').json()['demo'] is True
    assert owner.post('/api/device/connect', json={'port': 'emulator', 'allow_writes': True}).status_code == 200
    client = engine.client
    assert owner.post('/api/device/connect', json={'port': '/dev/this-must-not-open', 'allow_writes': True}).status_code == 400
    assert engine.client is client
    assert owner.post('/api/device/push-full', json={'confirm': 'OVERWRITE'}).status_code == 200
    assert owner.patch('/api/channels/C', json={'gain_db': -7}).status_code == 200


def test_demo_engine_rejects_a_transport_disguised_as_an_emulator_before_io(tmp_path):
    class ForbiddenTransport:
        def write(self, _): pytest.fail('physical write')
        def reset_input_buffer(self): pytest.fail('physical access')
    engine = create_demo_engine(tmp_path)
    with pytest.raises(EngineError, match='in-memory emulator'):
        engine.attach(Client(ForbiddenTransport()), 'emulator')
    with pytest.raises(EngineError, match='in-memory emulator'):
        engine.attach(Client(EmulatedDevice()), 'serial')


def test_demo_cli_does_not_search_for_vendor_map(tmp_path, monkeypatch, capsys):
    import uvicorn
    import helixtune.cli as cli
    def forbidden(*args): pytest.fail('Demo searched for a vendor parameter map')
    monkeypatch.setattr(cli, 'find_param_map', forbidden)
    served = []
    monkeypatch.setattr(uvicorn, 'run', lambda app, **kwargs: served.append((app, kwargs)))
    assert main(['demo', '--data', str(tmp_path), '--port', '8778']) == 0
    app, options = served[0]
    assert options['host'] == '127.0.0.1' and options['port'] == 8778
    assert owner_client(app).get('/api/status').json()['demo'] is True
    assert 'physical device connections are disabled' in capsys.readouterr().out


def test_demo_still_requires_auth_and_owner_device_capability(tmp_path):
    from fastapi.testclient import TestClient
    app = create_app(create_demo_engine(tmp_path))
    assert TestClient(app).get('/api/status').status_code == 401
    agent = TestClient(app, headers={'Authorization': f'Bearer {app.state.access.token("agent")}'})
    assert agent.get('/api/status').status_code == 200
    assert agent.post('/api/device/connect', json={'port': 'emulator'}).status_code == 403
