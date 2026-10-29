"""Synthetic regressions for authority, durable retention and per-source review."""
import json

import pytest

from helixtune import equipment, safety
from helixtune.api import create_app
from helixtune.engine import Engine, EngineError, SafetyRejected
from helixtune.emulator import EmulatedDevice
from helixtune.model import Crossover, Role
from helixtune.protocol.client import Client
from conftest import owner_client


@pytest.fixture
def setup(tmp_path, synthetic_mapping):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    def configure(tune):
        tune.channel('A').hp = Crossover(freq_hz=3000, slope_db=24)
        tune.channel('A').role = Role.TWEETER
    engine.edit('test', 'synthetic tweeter', configure)
    driver = equipment.Component(kind='speaker', channels=['A'], make='Synthetic', model='Driver',
        specs={'hp_min': equipment.Spec(value=2600, unit='Hz', source='manufacturer+confirmed')})
    engine.design.components.append(driver)
    engine.save_design()
    return engine, driver


def spec_item(engine):
    return next(item for item in engine.protection_book.constraints.values()
                if item.current and item.source.get('spec_key') == 'hp_min')


def act(engine, item, action, reason='Checked exact datasheet and physical output wiring'):
    return engine.review_protection(item.id, action, reason, item.review_fingerprint)


def test_agent_source_text_is_not_confirmation_and_pending_enforces(setup):
    engine, _ = setup
    item = spec_item(engine)
    assert item.state == 'pending' and not item.history
    with pytest.raises(SafetyRejected):
        engine.edit('agent', 'lower crossover', lambda t: setattr(t.channel('A'), 'hp', Crossover(freq_hz=2000)))


@pytest.mark.parametrize('change', ['value', 'unit', 'source', 'assignment', 'model', 'delete'])
def test_source_changes_invalidate_confirmation_and_retain_old_limit(setup, synthetic_mapping, change):
    engine, driver = setup
    old = spec_item(engine)
    act(engine, old, 'confirm')
    if change == 'value': driver.specs['hp_min'].value = 1800.0
    elif change == 'unit': driver.specs['hp_min'].unit = 'kHz'
    elif change == 'source': driver.specs['hp_min'].source = 'different revision'
    elif change == 'assignment': driver.channels = ['B']
    elif change == 'model': driver.model = 'Other'
    else: driver.specs.clear()
    engine.save_design()
    retained = engine.protection_book.constraints[old.id]
    assert retained.state == 'pending' and not retained.current
    assert [h.action for h in retained.history] == ['confirm', 'invalidate']
    assert engine.protections.outputs['A'].min_hp_hz == 2600
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.protections.outputs['A'].min_hp_hz == 2600
    assert again.protection_book.constraints[old.id].model_dump() == retained.model_dump()
    assert all(c.state == 'pending' for c in again.protection_book.constraints.values())


def test_presentation_edits_preserve_confirmation(setup):
    engine, driver = setup
    item = spec_item(engine)
    act(engine, item, 'confirm')
    driver.name, driver.notes, driver.location = 'Friendly name', 'Notes', 'Door'
    engine.save_design()
    assert spec_item(engine).state == 'confirmed'


def test_review_requires_reason_exact_revision_and_live_source(setup):
    engine, driver = setup
    item = spec_item(engine)
    with pytest.raises(EngineError, match='reason'): act(engine, item, 'confirm', ' ')
    act(engine, item, 'confirm')
    with pytest.raises(EngineError, match='refresh'): act(engine, item, 'confirm')
    driver.specs.clear()
    engine.save_design()
    orphan = engine.protection_book.constraints[item.id]
    with pytest.raises(EngineError, match='current'): act(engine, orphan, 'confirm')


def test_clear_is_individual_offline_audited_and_survives_restart(setup, synthetic_mapping):
    engine, driver = setup
    item = spec_item(engine)
    with pytest.raises(EngineError, match='source first'): act(engine, item, 'clear')
    driver.specs.clear()
    engine.save_design()
    item = engine.protection_book.constraints[item.id]
    engine.attach(Client(EmulatedDevice()), 'emulator')
    with pytest.raises(EngineError, match='disconnect'): act(engine, item, 'clear')
    engine.detach()
    act(engine, item, 'clear', 'Wrong datasheet removed; physical driver verified')
    assert engine.protections.outputs['A'].min_hp_hz == 1500  # role floor survives
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    cleared = again.protection_book.constraints[item.id]
    assert cleared.state == 'cleared'
    assert cleared.history[-1].reason == 'Wrong datasheet removed; physical driver verified'
    assert again.protections.outputs['A'].min_hp_hz == 1500
    # Reintroducing the exact source requires a new review, never resurrects authority.
    again.design.get(driver.id).specs['hp_min'] = equipment.Spec(value=2600, unit='Hz', source='manufacturer+confirmed')
    again.save_design()
    assert again.protection_book.constraints[item.id].state == 'pending'
    assert again.protections.outputs['A'].min_hp_hz == 2600


def test_returning_source_does_not_restore_confirmation(setup):
    engine, driver = setup
    item = spec_item(engine)
    act(engine, item, 'confirm')
    original = driver.specs['hp_min'].model_copy()
    driver.specs.clear()
    engine.save_design()
    driver.specs['hp_min'] = original
    engine.save_design()
    assert spec_item(engine).state == 'pending'


def test_v1_migration_keeps_all_limits_pending_and_tune_bytes(setup, synthetic_mapping):
    engine, _ = setup
    old = safety.OutputProtections()
    old.outputs['A'] = safety.OutputProtection(min_hp_hz=2900, min_hp_slope_db=24, max_lp_hz=10000, fs_factor=2)
    (engine.data_dir / 'protections.json').write_text(old.model_dump_json())
    tune_before = (engine.data_dir / 'current.json').read_bytes()
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.protections.outputs['A'] == old.outputs['A']
    assert (engine.data_dir / 'current.json').read_bytes() == tune_before
    legacy = [c for c in again.protection_book.constraints.values() if c.source['kind'] == 'legacy']
    assert len(legacy) == 4 and all(c.state == 'pending' and not c.current for c in legacy)
    assert json.loads((engine.data_dir / 'protections.json').read_text())['version'] == 2


def test_api_review_is_owner_only_and_requires_exact_payload(setup):
    engine, _ = setup
    app = create_app(engine)
    owner = owner_client(app)
    item = spec_item(engine)
    path = f'/api/protections/constraints/{item.id}/review'
    assert owner.post(path, json={'action': 'confirm'}).status_code == 422
    body = dict(action='confirm', reason='Verified datasheet and wiring', expected_fingerprint=item.review_fingerprint)
    from fastapi.testclient import TestClient
    agent = TestClient(app, headers={'Authorization': f'Bearer {app.state.access.token("agent")}'})
    assert agent.post(path, json=body).status_code == 403
    assert owner.post(path, json=body).status_code == 200
    assert owner.post(path, json=body).status_code == 400  # stale review
    shown = owner.get('/api/protections').json()['constraints'][item.id]
    assert shown['state'] == 'confirmed' and shown['history'][-1]['actor'] == 'owner'


@pytest.mark.parametrize('value', ['not a number', float('nan'), float('inf'), -1, 100000])
def test_invalid_constraint_metadata_cannot_poison_saved_state(setup, synthetic_mapping, value):
    engine, driver = setup
    driver.specs['hp_min'] = equipment.Spec(value=value, unit='Hz', source='invalid synthetic')
    with pytest.raises(EngineError, match='Invalid system design'): engine.save_design()
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.protections.outputs['A'].min_hp_hz == 2600


def test_confirmation_survives_restart_without_creating_new_sources(setup, synthetic_mapping):
    engine, _ = setup
    item = spec_item(engine)
    act(engine, item, 'confirm')
    before = engine.protection_book.model_dump()
    again = Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert again.protection_book.model_dump() == before
    assert spec_item(again).state == 'confirmed'


def test_corrupt_constraint_identity_fails_closed(setup, synthetic_mapping):
    engine, _ = setup
    path = engine.data_dir / 'protections.json'
    raw = json.loads(path.read_text())
    raw['constraints'][spec_item(engine).id]['value'] = 1500
    path.write_text(json.dumps(raw))
    backup = path.with_name('protections.json.bak')
    backup.unlink(missing_ok=True)                      # no backup: refuse to start, never default
    with pytest.raises(EngineError, match='no usable backup'):
        Engine(mapping=synthetic_mapping, data_dir=engine.data_dir)
    assert json.loads(path.read_text())['constraints'][spec_item(engine).id]['value'] == 1500   # evidence untouched
