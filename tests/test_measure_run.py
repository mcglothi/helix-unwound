"""Automated seat measurement (pink noise + RTA per output) against a simulated REW and the emulator."""
import base64
import json
import uuid

import httpx
import numpy as np
import pytest

from conftest import owner_client
from helixtune import measure_run
from helixtune.api import create_app
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.equipment import Component, Kind, SystemDesign
from helixtune.protocol.client import Client
from helixtune.rew import RewClient


class FakeRew:
    """Simulated REW API: records commands; 'Save current' stores the averaged trace of
    whichever output is the only unmuted one in the engine at that moment."""

    def __init__(self, engine):
        self.engine, self.log, self.rows, self.data = engine, [], [], {}
        self.save_creates = True
        self.rta_window_open = True
        self.hooks = {}            # (path, command) -> callable run before replying
        self.unmuted_at_play = None

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        path = req.url.path
        assert req.url.host == '127.0.0.1'
        self.log.append((req.method, path, body))
        if req.method == 'GET' and path == '/measurements' and ('GET', '/measurements') in self.hooks:
            self.hooks[('GET', '/measurements')]()
        if req.method == 'GET' and path == '/doc.json':
            return httpx.Response(200, json={'info': {'version': 'fake'}, 'paths': {
                '/measurements': {}, '/measurements/{id}/frequency-response': {}}})
        if req.method == 'GET' and path == '/rta/status':
            return httpx.Response(200, json={'enabled': self.rta_window_open, 'running': False})
        if req.method == 'GET' and path == '/measurements':
            return httpx.Response(200, json=self.rows)
        if req.method == 'GET' and path.endswith('/frequency-response'):
            return httpx.Response(200, json=self.data[path.split('/')[2]])
        hook = self.hooks.get((path, (body or {}).get('command') if isinstance(body, dict) else None))
        if hook:
            hook()
        if path == '/generator/command' and body == {'command': 'Play'}:
            self.unmuted_at_play = [c.id for c in self.engine.tune.channels if not c.mute]
        if path == '/rta/command' and body == {'command': 'Save current'} and self.save_creates:
            playing = [c.id for c in self.engine.tune.channels if not c.mute]
            uid = str(uuid.uuid4())
            mag = np.array([80.0 + 2 * len(playing), 81.0, 82.0], dtype='>f4')
            self.rows.append({'uuid': uid, 'title': f'RTA {len(self.rows) + 1}', 'notes': '', 'date': ''})
            self.data[uid] = {'unit': 'SPL', 'smoothing': 'None', 'startFreq': 20, 'ppo': 1,
                              'magnitude': base64.b64encode(mag.tobytes()).decode(), 'playing': playing}
        return httpx.Response(202, json={'message': 'ok'})

    def commands(self, path):
        return [b['command'] for m, p, b in self.log if p == path and b]


@pytest.fixture
def setup(synthetic_mapping, tmp_path):
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    e.design = SystemDesign(components=[Component(id=f'd{c}', kind=Kind.SPEAKER, make='M', model=c, channels=[c])
                                        for c in 'ABCDEF'])
    for cid in 'GHIJ':
        e.tune.channel(cid).mute = True
    e.tune.channel('A').link_group = e.tune.channel('B').link_group = 2
    e.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), 'emulator')
    e.push_full('OVERWRITE')
    fake = FakeRew(e)
    transport = httpx.MockTransport(fake.handler)
    e.rew_control_factory = lambda port: measure_run.RewControl(port, transport=transport)
    e.rew_reader_factory = lambda port: RewClient(port, transport=transport)
    yield e, fake
    if e.client is not None:
        e.detach()


def run(e, outputs, sleep=None, **kw):
    r = e.prepare_measure_run(outputs=outputs, seat=kw.pop('seat', 'Driver'), seconds=kw.pop('seconds', 3),
                              settle_s=0.5, level_dbfs=-24, source=kw.pop('source', 'rew'))
    r.sleep = sleep or (lambda s: None)
    clock = [0.0]

    def tick():
        clock[0] += 0.1
        return clock[0]
    r.clock = tick
    return r.execute()


def test_each_output_is_captured_alone_tagged_and_mutes_are_restored(setup):
    e, fake = setup
    before = {c.id: c.mute for c in e.tune.channels}
    st = run(e, ['A', 'B', 'C'])
    assert st.status == 'done' and [c['output'] for c in st.captures] == ['A', 'B', 'C']
    for cap in st.captures:
        m = e.measurements.get(cap['measurement_id'])
        assert m.channels == [cap['output']] and m.seat == 'driver' and m.kind == 'rta' and m.phase is None
        assert [c.id for c in m.tune.channels if not c.mute] == [cap['output']]   # exact isolated tune
        assert e.measurement_status(m) == ('current', '')
        ctx = m.import_provenance['capture_context']
        assert ctx['kind'] == 'measure_run' and 'magnitude only' in ctx['method']
        assert fake.data[cap['rew_uuid']]['playing'] == [cap['output']]           # linked B stayed muted for A
    assert {c.id: c.mute for c in e.tune.channels} == before and st.restored
    assert fake.commands('/rta/command').count('Reset averaging') == 3
    assert fake.commands('/generator/command') == ['Play', 'Stop'] and fake.commands('/rta/command')[-1] == 'Stop'
    assert json.loads((e.data_dir / measure_run.RUN_FILE).read_text())['status'] == 'done'


def test_external_noise_source_never_touches_the_generator(setup):
    e, fake = setup
    assert run(e, ['C'], source='external').status == 'done'
    assert fake.commands('/generator/command') == [] and not any(p == '/generator/signal' for _, p, _ in fake.log)


def test_stop_halts_rew_and_restores(setup):
    e, fake = setup
    before = {c.id: c.mute for c in e.tune.channels}
    holder = {}
    calls = [0]

    def sleep(s):
        calls[0] += 1
        if calls[0] == 3:
            holder['r'].stop()
    r = e.prepare_measure_run(outputs=['A', 'C'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')
    holder['r'] = r
    r.sleep = sleep
    st = r.execute()
    assert st.status == 'stopped' and st.captures == []
    assert fake.commands('/generator/command')[-1] == 'Stop' and fake.commands('/rta/command')[-1] == 'Stop'
    assert {c.id: c.mute for c in e.tune.channels} == before


def test_a_concurrent_edit_aborts_the_run(setup):
    e, _ = setup
    calls = [0]

    def sleep(s):
        calls[0] += 1
        if calls[0] == 2:
            e.edit('owner', 'someone else', lambda t: setattr(t.channel('C'), 'gain_db', -2.0))
    st = run(e, ['A', 'C'], sleep=sleep)
    # Codex review of 1515015: after someone else's edit the run's mutes cannot be told apart
    # from the owner's, so nothing is restored automatically; the owner decides.
    assert st.status == 'failed' and 'changed during the run' in st.error and not st.restored
    assert 'NOT restored automatically' in st.error and e.status()['interrupted_measure_run']['changed'] == st.changed


def test_a_lost_connection_aborts_without_blind_restoration(setup):
    e, _ = setup
    calls = [0]

    def sleep(s):
        calls[0] += 1
        if calls[0] == 2:
            e.device.needs_reconnect = True
    st = run(e, ['A', 'C'], sleep=sleep)
    assert st.status == 'failed' and not st.restored and 'NOT restored' in st.error
    assert e.tune.channel('C').mute                                             # left as the run set it
    assert json.loads((e.data_dir / measure_run.RUN_FILE).read_text())['restored'] is False


def test_rew_not_saving_fails_cleanly(setup):
    e, fake = setup
    fake.save_creates = False
    st = run(e, ['C'])
    assert st.status == 'failed' and 'exactly one new RTA measurement' in st.error and st.restored


@pytest.mark.parametrize('prep, match', [
    (lambda e: e.detach(), 'Connect a DSP'),
    (lambda e: setattr(e.device, 'sync_state', 'uncertain'), 'synchronized'),
    (lambda e: e.edit('t', 'mute C', lambda t: setattr(t.channel('C'), 'mute', True)), 'muted'),
    (lambda e: setattr(e, 'state_faults', ['x']), 'restored from a backup'),
])
def test_start_preconditions(setup, prep, match):
    e, _ = setup
    prep(e)
    with pytest.raises(EngineError, match=match):
        e.prepare_measure_run(outputs=['C'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')


def test_outputs_without_recorded_drivers_are_refused(setup):
    e, _ = setup
    e.tune.channel('G').mute = False
    with pytest.raises(EngineError, match='drivers'):
        e.prepare_measure_run(outputs=['G'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')


def test_an_interrupted_run_is_reported_after_restart(setup, synthetic_mapping):
    e, _ = setup
    state = measure_run.new_state(['A', 'C'], 'driver', 3, 0.5, -24, 'rew')
    state.changed, state.original_mutes = ['B', 'C'], {c.id: c.mute for c in e.tune.channels}
    (e.data_dir / measure_run.RUN_FILE).write_text(json.dumps(state.view()))       # running, as at a crash
    e.detach()
    again = Engine(mapping=synthetic_mapping, data_dir=e.data_dir)
    info = again.status()['interrupted_measure_run']
    assert info and info['changed'] == ['B', 'C']
    again.resolve_interrupted_measure_run('discard')
    assert again.status()['interrupted_measure_run'] is None


def test_api_is_owner_only_and_reports_progress(setup):
    e, _ = setup
    app = create_app(e)
    from fastapi.testclient import TestClient
    with TestClient(app, headers={'Authorization': f"Bearer {app.state.access.token('agent')}"}) as agent:
        assert agent.post('/api/measure/runs', json={'outputs': ['C'], 'seat': 'driver'}).status_code == 403
    with owner_client(app) as c:
        assert c.get('/api/measure/runs/current').json() is None


def test_a_closed_rta_window_is_reported_before_anything_is_muted(setup):
    e, fake = setup
    fake.rta_window_open = False
    before = {c.id: c.mute for c in e.tune.channels}
    st = run(e, ['C'])
    assert st.status == 'failed' and "RTA window" in st.error
    assert {c.id: c.mute for c in e.tune.channels} == before and st.changed == []


# ---- Codex review of 1515015 ----------------------------------------------------------------

def test_noise_starts_only_after_the_first_output_is_isolated(setup):
    e, fake = setup
    run(e, ['C', 'D'])
    assert fake.unmuted_at_play == ['C']


def test_no_second_run_can_start_while_the_first_is_cleaning_up(setup):
    e, fake = setup
    seen = {}

    def try_second():
        try:
            e.prepare_measure_run(outputs=['D'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')
            seen['second'] = 'admitted'
        except EngineError as exc:
            seen['second'] = str(exc)
    fake.hooks[('/generator/command', 'Stop')] = try_second
    assert run(e, ['C']).status == 'done'
    assert 'already in progress' in seen['second']


def test_recovery_intent_is_recorded_before_the_isolating_edit(setup, monkeypatch):
    e, _ = setup
    real_edit = e.edit
    seen = {}

    def edit(source, summary, fn):
        if summary.startswith('measure run: isolate'):
            seen['record'] = json.loads((e.data_dir / measure_run.RUN_FILE).read_text())
            raise RuntimeError('process died here')
        return real_edit(source, summary, fn)
    monkeypatch.setattr(e, 'edit', edit)
    st = run(e, ['A'])
    assert st.status == 'failed' and sorted(seen['record']['changed']) == ['B', 'C', 'D', 'E', 'F']
    assert seen['record']['status'] == 'running'


def test_stop_is_honoured_while_waiting_for_rew_to_save(setup):
    e, fake = setup
    fake.save_creates = False
    polls = [0]
    holder = {}

    def on_list():
        polls[0] += 1
        if polls[0] == 3:
            holder['r'].stop()
    fake.hooks[('GET', '/measurements')] = on_list
    r = e.prepare_measure_run(outputs=['C'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')
    holder['r'] = r
    r.sleep = lambda s: None
    clock = [0.0]
    r.clock = lambda: clock.__setitem__(0, clock[0] + 0.1) or clock[0]
    st = r.execute()
    assert st.status == 'stopped' and polls[0] < 10, st.error


# ---- Codex review of 2d92b31 ----------------------------------------------------------------

def test_a_timed_out_play_is_still_stopped(setup):
    e, fake = setup

    def play_times_out():
        raise httpx.ReadTimeout('REW accepted Play but the reply was lost')
    fake.hooks[('/generator/command', 'Play')] = play_times_out
    st = run(e, ['C'])
    assert st.status == 'failed' and fake.commands('/generator/command')[-1] == 'Stop'


def test_no_admission_during_the_final_save(setup, monkeypatch):
    e, _ = setup
    r = e.prepare_measure_run(outputs=['C'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')
    r.sleep = lambda s: None
    clock = [0.0]
    r.clock = lambda: clock.__setitem__(0, clock[0] + 0.1) or clock[0]
    real_save, seen = r._save, {}

    def save():
        real_save()
        if r.state.status != 'running' and 'second' not in seen:
            try:
                e.prepare_measure_run(outputs=['D'], seat='driver', seconds=3, settle_s=0.5, level_dbfs=-24, source='rew')
                seen['second'] = 'admitted'
            except EngineError as exc:
                seen['second'] = str(exc)
    monkeypatch.setattr(r, '_save', save)
    assert r.execute().status == 'done' and 'already in progress' in seen['second']
