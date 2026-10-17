"""Durable, independently reviewed constraints; tune metadata never grants authority."""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Literal

from pydantic import BaseModel, Field

from . import equipment, safety
from .model import Tune

LimitField = Literal['min_hp_hz', 'min_hp_slope_db', 'max_lp_hz', 'fs_factor']


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Review(BaseModel):
    action: Literal['confirm', 'clear', 'invalidate', 'restore']
    reason: str
    at: float = Field(default_factory=time.time)
    actor: Literal['owner', 'system']


class Constraint(BaseModel):
    id: str
    output: Literal['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    field: LimitField
    value: float = Field(allow_inf_nan=False)
    unit: str
    source: dict
    current: bool = True
    state: Literal['pending', 'confirmed', 'cleared'] = 'pending'
    history: list[Review] = Field(default_factory=list)

    @property
    def review_fingerprint(self) -> str:
        return fingerprint(self.model_dump())


class ProtectionBook(BaseModel):
    version: Literal[2] = 2
    constraints: dict[str, Constraint] = Field(default_factory=dict)

    def is_advisory(self, item: Constraint) -> bool:
        """Yellow tier: the Fs-multiple high-pass margin of a driver whose manufacturer
        publishes its own minimum high-pass. The manufacturer figure (red tier) governs;
        the margin is reported, not enforced. Without a manufacturer minimum the Fs margin
        is the only driver-specific floor and stays enforced."""
        src = item.source
        if item.field != 'min_hp_hz' or src.get('kind') != 'equipment' or src.get('spec_key') != 'fs':
            return False
        driver = (src.get('driver') or {}).get('id')
        return any(other.state != 'cleared' and other.output == item.output and other.field == 'min_hp_hz'
                   and other.source.get('kind') == 'equipment' and other.source.get('spec_key') == 'hp_min'
                   and (other.source.get('driver') or {}).get('id') == driver
                   for other in self.constraints.values())

    def effective(self, include_advisory: bool = False) -> safety.OutputProtections:
        """Enforced (red) limits; include_advisory=True adds the yellow-tier margins."""
        result = safety.OutputProtections()
        for key, item in self.constraints.items():
            payload = item.model_dump(include={'output', 'field', 'value', 'unit', 'source'})
            if key != item.id or item.id != fingerprint(payload):
                raise ValueError('Invalid protection source fingerprint')
            safety.OutputProtection.model_validate({item.field: item.value})
            if item.state == 'cleared' or (not include_advisory and self.is_advisory(item)):
                continue
            guard = result.outputs[item.output]
            old = getattr(guard, item.field)
            value = min(old, item.value) if item.field == 'max_lp_hz' and old is not None else max(old or 0, item.value)
            setattr(guard, item.field, int(value) if item.field == 'min_hp_slope_db' else value)
        return safety.OutputProtections.model_validate(result.model_dump())

    def view(self) -> dict:
        return {**self.model_dump(), 'outputs': self.effective().model_dump()['outputs'],
                'advisory_outputs': self.effective(include_advisory=True).model_dump()['outputs'],
                'constraints': {key: {**item.model_dump(), 'fingerprint': item.review_fingerprint,
                                      'advisory': self.is_advisory(item)}
                                for key, item in self.constraints.items()}}


def load(encoded: str | None) -> ProtectionBook:
    if encoded is None:
        return ProtectionBook()
    raw = json.loads(encoded)
    if raw.get('version') != 1:
        book = ProtectionBook.model_validate(raw)
        book.effective()  # fail closed on invalid persisted numeric constraints
        return book
    legacy = safety.OutputProtections.model_validate(raw)
    book = ProtectionBook()
    for cid, guard in legacy.outputs.items():
        for field, value in guard.model_dump().items():
            if value is None or value == 0 or (field == 'min_hp_slope_db' and value == 12):
                continue
            item = candidate(cid, field, value, {'kind': 'legacy', 'revision': 1, 'note': 'Imported aggregate; original source unknown'})
            item.current = False
            book.constraints[item.id] = item
    return book


def candidate(cid: str, field: LimitField, value: float, source: dict) -> Constraint:
    # Validate numerical limits before they can enter durable state.
    safety.OutputProtection.model_validate({field: value})
    unit = 'Hz' if field in ('min_hp_hz', 'max_lp_hz') else 'dB/oct' if field == 'min_hp_slope_db' else '× Fs'
    payload = dict(output=cid, field=field, value=float(value), unit=unit, source=source)
    return Constraint(id=fingerprint(payload), **payload)


def reconcile(book: ProtectionBook, tune: Tune, policy: safety.SafetyPolicy,
              design: equipment.SystemDesign) -> ProtectionBook:
    """Pure preview or persisted reconciliation; never drops a retained limit."""
    result = book.model_copy(deep=True)
    live: dict[str, Constraint] = {}

    def add(cid, field, value, source):
        if value is not None and value != 0:
            item = candidate(cid, field, value, source)
            live[item.id] = item

    retained = book.effective()
    for ch in tune.channels:
        rp = policy.roles.get(ch.role)
        assignments = sorted([{'id': c.id, 'make': c.make, 'model': c.model, 'serial': c.serial,
                               'channels': sorted(c.channels)} for c in design.components
                              if c.kind in (equipment.Kind.SPEAKER, equipment.Kind.SUBWOOFER) and ch.id in c.channels],
                             key=lambda x: x['id'])
        role_source = {'kind': 'role', 'role': ch.role.value, 'policy': rp.model_dump() if rp else None,
                       'drivers': assignments}
        if rp:
            add(ch.id, 'min_hp_hz', rp.min_hp_hz, role_source)
            if rp.min_hp_hz:
                add(ch.id, 'min_hp_slope_db', rp.min_hp_slope_db, role_source)
            add(ch.id, 'fs_factor', rp.fs_factor, role_source)
        # A historical multiplier remains enforced even after relabelling the role.
        retained_factor = retained.outputs[ch.id].fs_factor
        factor = max(retained_factor, (rp.fs_factor or 0) if rp else 0)
        for c in design.components:
            if c.kind not in (equipment.Kind.SPEAKER, equipment.Kind.SUBWOOFER) or ch.id not in c.channels:
                continue
            identity = {'id': c.id, 'make': c.make, 'model': c.model, 'serial': c.serial,
                        'kind': c.kind.value, 'channels': sorted(c.channels)}
            for spec_key, field in [('hp_min', 'min_hp_hz'), ('hp_min_slope', 'min_hp_slope_db'),
                                    ('lp_max', 'max_lp_hz'), ('fs', 'min_hp_hz')]:
                spec = c.specs.get(spec_key)
                if spec is None:
                    continue
                try:
                    value = float(spec.value)
                except (ValueError, TypeError):
                    raise ValueError(f'{c.id}: {spec_key} must be numeric') from None
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f'{c.id}: {spec_key} must be finite and positive')
                source = {'kind': 'equipment', 'driver': identity, 'spec_key': spec_key,
                          'spec': spec.model_dump(), 'spec_source': c.spec_source}
                if spec_key == 'fs':
                    source['factor'] = factor
                    source['role'] = role_source
                    value *= factor
                add(ch.id, field, value, source)
    for key, item in result.constraints.items():
        current = key in live
        if not current and item.state == 'confirmed':
            item.state = 'pending'
            item.history.append(Review(action='invalidate', actor='system', reason='Source values, units, identity, assignment or policy changed/removed'))
        if current and not item.current and item.state == 'cleared':
            item.state = 'pending'
            item.history.append(Review(action='restore', actor='system', reason='Previously cleared source returned; review required'))
        item.current = current
    for key, item in live.items():
        result.constraints.setdefault(key, item)
    result.effective()
    return result


def review(book: ProtectionBook, key: str, action: Literal['confirm', 'clear'], reason: str,
           expected_fingerprint: str) -> ProtectionBook:
    result = book.model_copy(deep=True)
    item = result.constraints[key]
    if expected_fingerprint != item.review_fingerprint:
        raise ValueError('Constraint changed; refresh before reviewing')
    if not reason.strip():
        raise ValueError('Review requires an evidence/reason')
    if action == 'confirm' and (not item.current or item.state != 'pending'):
        raise ValueError('Only a current, enforced source can be confirmed')
    if action == 'clear' and item.current:
        raise ValueError('Correct or remove the source first, then clear its retained constraint')
    if action == 'clear' and item.state == 'cleared':
        raise ValueError('Constraint is already cleared')
    item.state = 'confirmed' if action == 'confirm' else 'cleared'
    item.history.append(Review(action=action, actor='owner', reason=reason.strip()))
    result.effective()
    return result
