import pytest
from conftest import owner_client
from helixtune.api import create_app
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.protocol.client import Client


@pytest.fixture
def engine(tmp_path, synthetic_mapping):
    return Engine(mapping=synthetic_mapping, data_dir=tmp_path)


def attach(engine):
    device = EmulatedDevice()
    engine.attach(Client(device, allow_writes=True), 'emulator')
    return device


def test_review_is_read_only_and_does_not_establish_baseline(engine):
    device = attach(engine)
    before = list(device.log)
    review = engine.overwrite_review()
    assert review['parameter_count'] > 1000 and review['problems'] == []
    assert review['context'] == engine.overwrite_review()['context']
    assert device.log == before and not engine.device.baselined


def test_changed_tune_refuses_reviewed_overwrite_before_any_write(engine):
    device = attach(engine)
    review = engine.overwrite_review()
    engine.edit('agent', 'change staged tune', lambda t: setattr(t.channel('A'), 'gain_db', -1))
    before = list(device.log)
    with pytest.raises(EngineError, match='review the overwrite again'):
        engine.push_full('OVERWRITE', review['context'])
    assert device.log == before
    engine.push_full('OVERWRITE', engine.overwrite_review()['context'])
    assert engine.device.baselined


def test_reconnecting_same_kind_invalidates_review(engine):
    attach(engine)
    review = engine.overwrite_review()
    engine.detach()
    replacement = attach(engine)
    before = list(replacement.log)
    with pytest.raises(EngineError, match='connection changed'):
        engine.push_full('OVERWRITE', review['context'])
    assert replacement.log == before


def test_review_from_previous_process_instance_is_not_reusable(engine, synthetic_mapping):
    attach(engine)
    old = engine.overwrite_review()['context']
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    attach(again)
    with pytest.raises(EngineError, match='review the overwrite again'):
        again.push_full('OVERWRITE', old)


def test_disconnect_closes_transport_and_invalidates_baseline(engine):
    class Closable(EmulatedDevice):
        closed = False
        def close(self): self.closed = True
    transport = Closable()
    engine.attach(Client(transport), 'emulator')
    epoch = engine.status()['connection_epoch']
    engine.detach()
    assert transport.closed and engine.client is None and engine.applied_image is None
    assert engine.device.kind == 'none' and engine.status()['connection_epoch'] > epoch


def test_failed_close_still_leaves_app_disconnected(engine):
    class BadClose(EmulatedDevice):
        def close(self): raise OSError('synthetic close failure')
    engine.attach(Client(BadClose()), 'emulator')
    with pytest.raises(EngineError, match='closing the transport failed'): engine.detach()
    assert engine.client is None and engine.device.kind == 'none'


def test_api_defaults_read_only_and_reviewed_push_requires_write_connection(engine):
    owner = owner_client(create_app(engine))
    assert owner.post('/api/device/connect', json={'port': 'emulator'}).status_code == 200
    review = owner.get('/api/device/review').json()
    assert not review['device']['writes_enabled']
    assert owner.post('/api/device/push-full', json={'confirm':'OVERWRITE','expected_context':review['context']}).status_code == 400
    owner.post('/api/device/disconnect')
    owner.post('/api/device/connect', json={'port':'emulator','allow_writes':True})
    review = owner.get('/api/device/review').json()
    owner.patch('/api/channels/A', json={'gain_db':-1})
    assert owner.post('/api/device/push-full', json={'confirm':'OVERWRITE','expected_context':review['context']}).status_code == 400
    review = owner.get('/api/device/review').json()
    assert owner.post('/api/device/push-full', json={'confirm':'OVERWRITE','expected_context':review['context']}).status_code == 200


def test_concurrent_connection_replacement_closes_superseded_transports(engine, monkeypatch):
    import serial
    import threading
    from concurrent.futures import ThreadPoolExecutor
    transports = []
    rendezvous = threading.Barrier(2)
    class Transport(EmulatedDevice):
        closed = False
        def close(self): self.closed = True
    def open_serial(*args, **kwargs):
        transport = Transport()
        transports.append(transport)
        try: rendezvous.wait(timeout=.1)
        except threading.BrokenBarrierError: pass
        return transport
    monkeypatch.setattr(serial, 'Serial', open_serial)
    app = create_app(engine)
    def connect(port): return owner_client(app).post('/api/device/connect', json={'port': port}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(connect, ['test-port-1', 'test-port-2']))
    assert results == [200, 200]
    assert sum(not t.closed for t in transports) == 1
    engine.detach()
    assert all(t.closed for t in transports)
