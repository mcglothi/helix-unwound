"""Atomic, versioned application state. Never contains a device connection/baseline.

current.json is a compatibility export; workstation.json is authoritative once
present. Keep the previous validated checkpoint for recovery from corruption.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .model import Tune


class Slots(BaseModel):
    A: Tune | None = None
    B: Tune | None = None
    active: Literal['A', 'B'] | None = None


class Checkpoint(BaseModel):
    version: Literal[1] = 1
    tune: Tune
    history: list[Tune] = Field(default_factory=list, max_length=200)
    redo: list[Tune] = Field(default_factory=list, max_length=200)
    ab: Slots = Field(default_factory=Slots)


class RecoveryError(RuntimeError):
    pass


def read(path: Path) -> Checkpoint:
    raw = json.loads(path.read_text())
    # A future format must not be silently replaced with an older backup.
    if isinstance(raw, dict) and raw.get('version', 1) != 1:
        raise RecoveryError('Unsupported workstation version; open it with a compatible application')
    return Checkpoint.model_validate(raw)


def load(directory: Path) -> tuple[Checkpoint | None, str | None]:
    primary = directory / 'workstation.json'
    backup = directory / 'workstation.previous.json'
    if not primary.exists() and not backup.exists():
        return None, None
    try:
        return read(primary), None
    except RecoveryError:
        raise
    except (OSError, ValueError):
        try:
            return read(backup), 'Recovered the previous saved session. The newest checkpoint could not be read; review the tune before continuing.'
        except (OSError, ValueError) as exc:
            raise RecoveryError('Saved session and recovery checkpoint could not be read. Preserve the data directory and restore a known-good backup; no default tune was substituted.') from exc


def atomic_write(path: Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        # Persist the directory entry as well as the file content on supported hosts.
        if os.name == 'posix':
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(directory: Path, state: Checkpoint) -> None:
    primary = directory / 'workstation.json'
    if primary.exists():
        try:
            previous = read(primary)
        except (OSError, ValueError):
            pass  # never replace a good recovery copy with a damaged primary
        else:
            atomic_write(directory / 'workstation.previous.json', previous.model_dump_json())
    atomic_write(primary, state.model_dump_json())
