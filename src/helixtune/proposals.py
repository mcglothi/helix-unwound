"""Proposals: computed changes that are previewed and reviewed before they are applied.

A proposal is a list of field edits (not a whole tune), so applying it later merges onto
whatever the tune is then, instead of reverting unrelated edits made in the meantime.

Each proposal is bound to what it was computed from: the before-value of every field it
changes, and its context (target curve, measurements, and the physical drivers on the
affected channels). Preview and apply both re-check that binding; a change to any of it
is a conflict, and the proposal must be recomputed. Unrelated edits stay mergeable.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .model import EqBand, Tune


class Edit(BaseModel):
    channel: str | None = None      # None = tune-level field
    field: str                      # e.g. "delay_ms", "gain_db", "eq"
    value: Any
    before: Any = None              # value when the proposal was computed (conflict check)
    label: str = ""                 # human-readable line


class ProposalContext(BaseModel):
    """Assumptions a proposal was computed from. Empty fields are not part of the binding."""

    seat: str | None = None
    target_mode: str | None = None                              # "shape" | "level" (how the solver target was built)
    target: str | None = None                                   # fingerprint of the exact target array the solver used
    anchor: dict[str, str] = Field(default_factory=dict)        # level-anchor measurement id -> content fingerprint
    measurements: dict[str, str] = Field(default_factory=dict)  # fitted measurement id -> content fingerprint
    drivers: dict[str, str] = Field(default_factory=dict)       # channel -> driver-identity fingerprint
    inputs: dict[str, str] = Field(default_factory=dict)        # channel -> fingerprint of solver-consumed settings


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    kind: str                       # auto_eq | alignment | levels
    title: str
    notes: list[str] = Field(default_factory=list)
    edits: list[Edit]
    metrics: dict[str, Any] = Field(default_factory=dict)
    context: ProposalContext = Field(default_factory=ProposalContext)
    created: float = Field(default_factory=time.time)
    source: str = "engine"

    def apply_to(self, tune: Tune) -> Tune:
        t = tune.model_copy(deep=True)
        for e in self.edits:
            target = t.channel(e.channel) if e.channel else t
            value = [EqBand.model_validate(b) for b in e.value] if e.field == "eq" else e.value
            setattr(target, e.field, value)
        return Tune.model_validate(t.model_dump())

    def field_conflicts(self, tune: Tune) -> list[str]:
        """Edits whose field changed since the proposal was computed."""
        out = []
        for e in self.edits:
            target = tune.channel(e.channel) if e.channel else tune
            if comparable(getattr(target, e.field)) != comparable(e.before):
                where = f"{e.channel} " if e.channel else ""
                out.append(f"{where}{e.field} changed since this proposal was computed")
        return out


class ProposalConflict(RuntimeError):
    def __init__(self, conflicts: list[str]):
        super().__init__("; ".join(conflicts))
        self.conflicts = conflicts


def _encode(o: Any) -> Any:
    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    if isinstance(o, Enum):
        return o.value
    raise TypeError(f"cannot compare {type(o).__name__}")


def comparable(value: Any) -> Any:
    """JSON-normal form, so model objects, enums and stored dicts compare equal."""
    return json.loads(json.dumps(value, default=_encode))


def fingerprint(value: Any) -> str:
    data = json.dumps(comparable(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()[:16]
