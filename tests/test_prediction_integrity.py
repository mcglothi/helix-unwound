import numpy as np
import pytest

from conftest import owner_client
from helixtune import equipment, measurements as M
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.model import Tune, Role


@pytest.fixture
def engine(tmp_path, synthetic_mapping):
    e = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    for cid in ['A', 'B', 'C']:
        e.tune.channel(cid).role = Role.FULLRANGE
        e.design.components.append(equipment.Component(kind='speaker', channels=[cid], make='Test', model=cid))
    e.save_design()
    return e


def capture(engine, channels, *, name='capture', level=80, when=1, trusted=True, baseline=True, seat='driver'):
    m = M.Measurement(name=name, channels=channels, freqs=M.GRID.tolist(), spl=[level] * len(M.GRID),
                      taken_at=when, seat=seat, tune=engine.tune.model_copy(deep=True) if baseline else None,
                      drivers={c: engine.driver_identity(c) for c in channels} if trusted else None)
    engine.measurements.save(m)
    return m


@pytest.mark.parametrize('channels', [['A'], ['A', 'B']])
def test_master_gain_delta_is_applied_once_outside_channel_transfer(channels):
    then = Tune(master_gain_db=-6)
    now = then.model_copy(deep=True)
    now.master_gain_db = -10
    m = M.Measurement(name='synthetic', channels=channels, freqs=M.GRID.tolist(), spl=[80]*len(M.GRID), tune=then)
    assert np.allclose(M.predict(m, now), 76)
    assert np.allclose(M.predict(m, then), 80)


def test_selection_rejects_unknown_stale_missing_baseline_and_overlapping_captures(engine):
    a = capture(engine, ['A'], name='old isolated', when=1)
    b = capture(engine, ['B'], name='isolated B', when=2)
    fresh = capture(engine, ['A'], name='new isolated', when=3, level=70)
    group = capture(engine, ['A', 'B'], name='combined', when=10, level=120)
    unknown = capture(engine, ['C'], name='unidentified', trusted=False, level=150)
    no_tune = capture(engine, ['C'], name='missing tune', baseline=False, level=150)
    stale = capture(engine, ['C'], name='old driver', level=150)
    engine.design.get(engine.driver_identity('C')[0]['id']).model = 'Replacement'
    engine.save_design()
    view = engine.system_view(smoothing=0)
    assert {m['id'] for m in view['contributors']} == {fresh.id, b.id}
    assert {m['id'] for m in view['excluded']} == {a.id, group.id, unknown.id, no_tune.id, stale.id}
    assert view['measurement_count'] == 2 and view['available_measurement_count'] == 7
    assert view['coverage'] == {'outputs': ['A', 'B'], 'missing_outputs': ['C']}
    assert view['predicted'][0] == pytest.approx(10 * np.log10(10**7 + 10**8), abs=.01)
    assert view['aggregation'] == 'power_sum' and not view['phase_verified']


def test_output_order_does_not_defeat_overlap_selection(engine):
    first = capture(engine, ['A', 'B'], name='older pair', when=1)
    latest = capture(engine, ['B', 'A'], name='new pair', when=2)
    view = engine.system_view()
    assert [m['id'] for m in view['contributors']] == [latest.id]
    assert view['excluded'][0]['id'] == first.id
    assert 'Overlaps' in view['excluded'][0]['reason']


def test_combined_capture_does_not_masquerade_as_individual_driver_curves(engine):
    capture(engine, ['A', 'B'])
    engine.tune.channel('B').role = Role.MIDRANGE
    view = engine.system_view()
    assert view['channels'] == {}
    assert set(view['groups']) == {'mixed'}
    assert any('individual output responses' in note for note in view['limitations'])


def test_master_change_moves_estimate_and_target_but_not_captured_trace(engine):
    m = capture(engine, ['A'])
    before = engine.system_view()
    engine.tune.master_gain_db -= 6
    after = engine.system_view()
    assert np.allclose(np.array(after['predicted']) - before['predicted'], -6)
    assert np.allclose(np.array(after['target']) - before['target'], -6)
    assert after['measured'] == before['measured']
    assert np.allclose(engine.measurement_curves(m.id)['predicted'], 74)


@pytest.mark.parametrize('change', ['routing', 'capture_mute', 'group_delay', 'group_polarity'])
def test_unmodellable_changes_refuse_projection_and_solver_use(engine, change):
    chans = ['A', 'B'] if change.startswith('group') else ['A']
    m = capture(engine, chans)
    if change == 'routing': engine.tune.channel('A').mix = {'R': 1}
    elif change == 'capture_mute':
        m.tune.channel('A').mute = True
        engine.measurements.save(m)
    elif change == 'group_delay': engine.tune.channel('A').delay_ms = 1
    else: engine.tune.channel('A').invert = True
    view = engine.system_view()
    assert not view['contributors'] and view['predicted'] is None
    assert view['excluded'] and not engine._anchor_measurements('driver')
    assert engine.measurement_curves(m.id)['predicted'] is None
    usable, notes = engine._usable_measurements('driver')
    assert not usable and notes


def test_historical_capture_remains_readable_without_projecting_onto_replacement(engine):
    m = capture(engine, ['A'], trusted=False)
    client = owner_client(create_app(engine))
    curves = client.get(f'/api/measurements/{m.id}/curves').json()
    assert curves['measured'] and curves['predicted'] is None
    assert curves['hardware_status'] == 'unknown' and curves['prediction_issues']


def test_empty_or_other_seat_captures_do_not_invent_a_target(engine):
    capture(engine, ['A'], seat='passenger')
    view = engine.system_view('driver')
    assert view['measurement_count'] == view['available_measurement_count'] == 0
    assert view['target'] is view['predicted'] is view['measured'] is None


def test_display_and_solver_anchor_share_exact_contributors(engine):
    capture(engine, ['A'], when=1)
    capture(engine, ['A', 'B'], when=2)
    capture(engine, ['C'], trusted=False, level=180)
    view = engine.system_view()
    _, anchor = engine.solver_target('driver', 'level')
    assert set(anchor) == {m['id'] for m in view['contributors']}
    # Channel C's unknown capture cannot move either target.
    assert max(view['target']) < 100


@pytest.mark.parametrize('field,value', [('delay_ms', 1), ('invert', True)])
def test_combined_capture_proposal_is_refused_after_phase_settings_change(engine, field, value):
    from helixtune.proposals import ProposalConflict
    capture(engine, ['A', 'B'])
    proposal = engine.propose_auto_eq(['A'])
    engine.edit('test', 'change phase setting', lambda t: setattr(t.channel('B'), field, value))
    with pytest.raises(ProposalConflict):
        engine.preview_proposal(proposal['id'])
    with pytest.raises(ProposalConflict):
        engine.apply_proposal(proposal['id'], 'agent')
