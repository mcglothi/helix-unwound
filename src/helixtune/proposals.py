"""Proposals: computed changes that are previewed and reviewed before they are applied.

A proposal is a list of field edits (not a whole tune), so applying it later merges onto
whatever the tune is then, instead of reverting unrelated edits made in the meantime.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from .model import EqBand, Tune


class Edit(BaseModel):
    channel: str | None = None      # None = tune-level field
    field: str                      # e.g. "delay_ms", "gain_db", "eq"
    value: Any
    before: Any = None
    label: str = ""                 # human-readable line


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    kind: str                       # auto_eq | alignment | levels
    title: str
    notes: list[str] = Field(default_factory=list)
    edits: list[Edit]
    metrics: dict[str, Any] = Field(default_factory=dict)
    created: float = Field(default_factory=time.time)
    source: str = "engine"

    def apply_to(self, tune: Tune) -> Tune:
        t = tune.model_copy(deep=True)
        for e in self.edits:
            target = t.channel(e.channel) if e.channel else t
            value = [EqBand.model_validate(b) for b in e.value] if e.field == "eq" else e.value
            setattr(target, e.field, value)
        return Tune.model_validate(t.model_dump())
