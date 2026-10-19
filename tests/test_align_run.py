"""Crossover summing time alignment (pink noise + RTA, delay sweep) against a simulated REW."""
import base64
import json

import httpx
import numpy as np
import pytest

from conftest import owner_client
from helixtune import measure_run
from helixtune.dsp.filters import XoType
from helixtune.emulator import EmulatedDevice
from helixtune.engine import Engine, EngineError
from helixtune.equipment import Component, Kind, SystemDesign
from helixtune.model import Crossover
from helixtune.protocol.client import Client
from helixtune.rew import RewClient
from test_measure_run import FakeRew

FC = 300.0


class SummingRew(FakeRew):
    """RTA data for two equal drivers summing at the crossover: band level follows
    |1 + e^{j 2 pi fc dt}|^2 where dt = (adjusted delay - acoustically ideal delay)."""

    def __init__(self, engine, reference='A', adjust='C', ideal_ms=1.0):
        super().__init__(engine)
        self.reference, self.adjust, self.ideal_ms = reference, adjust, ideal_ms
        self.signal, self.floor, self.jitter, self.reads = 77.0, 40.0, 0.0, 0

    def handler(self, req):
        if req.method == 'GET' and req.url.path == '/rta/captured-data':
            self.log.append((req.method, req.url.path, None))
            playing = {c.id for c in self.engine.tune.channels if not c.mute}
            dt = (self.engine.tune.channel(self.adjust).delay_ms - self.ideal_ms) / 1000
            level = self.signal + 10 * np.log10(2 + 2 * np.cos(2 * np.pi * FC * dt) + 1e-3)
            if not playing:
                level = self.floor
            self.reads += 1
            level += self.jitter * (1 if self.reads % 2 else -1)
            spl = np.full(4096, level, dtype='>f4')
            return httpx.Response(200, json={'unit': 'SPL', 'startFreq': 0.0, 'freqStep': 1.0,
                                             'magnitude': base64.b64encode(spl.tobytes()).decode()})
        return super().handler(req)


@pytest.fixture
def setup(synthetic_mapping, tmp_path):
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    e.design = SystemDesign(components=[Component(id=f'd{c}', kind=Kind.SPEAKER, make='M', model=c, channels=[c])
                                        for c in 'ABCDEF'])
    for cid in 'GHIJ':
        e.tune.channel(cid).mute = True
    e.tune.channel('A').lp = Crossover(type=XoType.LINKWITZ_RILEY, slope_db=24, freq_hz=FC)
    e.tune.channel('C').hp = Crossover(type=XoType.LINKWITZ_RILEY, slope_db=24, freq_hz=FC)
    e.tune.channel('C').delay_ms = 2.0
    e.tune.channel('E').delay_ms = 2.5
    e.attach(Client(EmulatedDevice(), allow_writes=True, timeout=0.05), 'emulator')
    e.push_full('OVERWRITE')
    fake = SummingRew(e)
    transport = httpx.MockTransport(fake.handler)
    e.rew_control_factory = lambda port: measure_run.RewControl(port, transport=transport)
    e.rew_reader_factory = lambda port: RewClient(port, transport=transport)
    yield e, fake
    if e.client is not None:
        e.detach()


def align(e, sleep=None, **kw):
    params = dict(reference='A', adjust='C', carry=[], seat='driver', steps=9, seconds=2, settle_s=0.2) | kw
    r = e.prepare_align_run(**params)
    r.sleep = sleep or (lambda s: None)
    clock = [0.0]
    r.clock = lambda: clock.__setitem__(0, clock[0] + 0.1) or clock[0]
    return r.execute()


def test_finds_the_summing_delay_restores_everything_and_proposes_it(setup):
    e, fake = setup
    fake.ideal_ms = 1.0                                   # C is 1 ms late
    before = e.tune.model_copy(deep=True)
    st = align(e, carry=['E'])
    a = st.align
    assert st.status == 'done' and st.restored and a['fc'] == FC
    assert abs(a['best_offset_ms'] - (-1.0)) <= (1000 / FC) / 8 + 1e-9   # within one step
    assert a['gain_db'] > 0.5 and a['proposal_id']
    assert e.tune.model_dump() == before.model_dump()     # delays and mutes back as they were
    p = e.proposal(a['proposal_id'])
    edits = {x.channel: (x.before, x.value) for x in p.edits}
    assert set(edits) == {'C', 'E'} and edits['C'][0] == 2.0 and edits['E'][0] == 2.5
    assert abs((edits['C'][1] - edits['C'][0]) - (edits['E'][1] - edits['E'][0])) < 1e-9   # carried together
    e.apply_proposal(a['proposal_id'], 'owner')
    assert abs(e.tune.channel('C').delay_ms - (2.0 + a['best_offset_ms'])) < 1e-9
    assert fake.commands('/rta/command').count('Reset averaging') == len(a['offsets']) + 2   # + floor + repeat


def test_only_the_pair_plays_during_the_sweep(setup):
    e, fake = setup
    seen = []
    real = fake.handler

    def spy(req):
        if req.url.path == '/rta/captured-data':
            seen.append(sorted(c.id for c in e.tune.channels if not c.mute))
        return real(req)
    fake.handler = spy
    transport = httpx.MockTransport(spy)
    e.rew_control_factory = lambda port: measure_run.RewControl(port, transport=transport)
    align(e)
    assert seen[0] == [] and seen[1:] and all(s == ['A', 'C'] for s in seen[1:])   # floor first, then the pair


def test_already_aligned_makes_no_proposal(setup):
    e, fake = setup
    fake.ideal_ms = 2.0                                   # current delay is ideal
    st = align(e)
    assert st.status == 'done' and 'proposal_id' not in st.align and 'Already aligned' in st.align['outcome']


def test_stop_restores_delays_and_mutes_and_proposes_nothing(setup):
    e, _ = setup
    before = e.tune.model_copy(deep=True)
    calls, holder = [0], {}

    def sleep(s):
        calls[0] += 1
        if calls[0] == 4:
            holder['r'].stop()
    r = e.prepare_align_run(reference='A', adjust='C', steps=9, seconds=2, settle_s=0.2)
    holder['r'] = r
    r.sleep = sleep
    st = r.execute()
    assert st.status == 'stopped' and 'proposal_id' not in st.align
    assert e.tune.model_dump() == before.model_dump()


def test_lost_connection_leaves_an_interrupted_run_that_restores_delays(setup):
    e, _ = setup
    calls = [0]

    def sleep(s):
        calls[0] += 1
        if calls[0] == 30:                                # during the first sweep step (after the floor)
            e.device.needs_reconnect = True
    st = align(e, sleep=sleep)
    assert st.status == 'failed' and not st.restored and 'C' in st.delay_changed
    info = e.status()['interrupted_measure_run']
    assert info['delay_changed'] == ['C'] and info['original_delays']['C'] == 2.0
    e.device.needs_reconnect = False
    e.resolve_interrupted_measure_run('restore')
    assert e.tune.channel('C').delay_ms == 2.0 and not e.tune.channel('B').mute


def test_recovery_intent_is_recorded_before_the_delay_edit(setup, monkeypatch):
    e, _ = setup
    real_edit, seen = e.edit, {}

    def edit(source, summary, fn):
        if summary.startswith('alignment run:'):
            seen['record'] = json.loads((e.data_dir / measure_run.RUN_FILE).read_text())
            raise RuntimeError('process died here')
        return real_edit(source, summary, fn)
    monkeypatch.setattr(e, 'edit', edit)
    st = align(e)
    assert st.status == 'failed' and seen['record']['delay_changed'] == ['C']
    assert seen['record']['original_delays'] == {'C': 2.0}


@pytest.mark.parametrize('kw, match', [
    (dict(reference='A', adjust='E'), 'do not share a crossover'),
    (dict(reference='A', adjust='C', steps=8), 'odd number'),
    (dict(reference='A', adjust='A'), 'two different outputs'),
    (dict(reference='A', adjust='C', carry=['A']), 'distinct'),
])
def test_preconditions(setup, kw, match):
    e, _ = setup
    with pytest.raises(EngineError, match=match):
        e.prepare_align_run(**kw)


def test_delays_never_go_negative(setup):
    e, _ = setup
    e.edit('owner', 'C at 0', lambda t: setattr(t.channel('C'), 'delay_ms', 0.0))
    with pytest.raises(EngineError, match='too little delay'):
        e.prepare_align_run(reference='A', adjust='C', steps=3, span_ms=1.0)
    r = e.prepare_align_run(reference='A', adjust='C', steps=9)
    assert min(r.state.align['offsets']) == 0.0


def test_align_api_is_owner_only(setup):
    e, _ = setup
    from fastapi.testclient import TestClient
    from helixtune.api import create_app
    app = create_app(e)
    with TestClient(app, headers={'Authorization': f"Bearer {app.state.access.token('agent')}"}) as agent:
        assert agent.post('/api/measure/align', json={'reference': 'A', 'adjust': 'C'}).status_code == 403


# ---- guards found by the live run (2026-10-19): no proposals from noise -----------------------

def test_signal_too_close_to_the_noise_floor_fails_without_a_proposal(setup):
    e, fake = setup
    fake.signal = 36.0                                    # pair ~ +3..6 dB over a 40 dB floor
    before = e.tune.model_copy(deep=True)
    st = align(e)
    assert st.status == 'failed' and 'above the cabin noise' in st.error and 'proposal_id' not in st.align
    assert e.tune.model_dump() == before.model_dump()


def test_an_unrepeatable_measurement_makes_no_proposal(setup):
    e, fake = setup
    fake.ideal_ms = 1.9                                   # true gain is tiny
    fake.jitter = 1.5                                     # alternating +-1.5 dB between reads
    st = align(e)
    assert st.status == 'done' and 'proposal_id' not in st.align and 'measurement noise' in st.align['outcome']
    assert st.align['repeatability_db'] > 0
