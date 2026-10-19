"""Power-loss-safe state files (the engine is meant to run on a truck computer that loses power
when the ignition goes off).

atomic_write: temp file in the same directory, flush + fsync, atomic replace, then fsync the
directory, so a reader sees either the old or the new complete file, never a truncated one.

write_with_backup / read_with_backup: critical state also keeps the previous complete version as
``<name>.bak``. If the primary cannot be parsed, startup uses the backup and reports it instead of
failing; if neither can be read, it fails with an actionable message and never substitutes defaults.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


class StateRecoveryError(RuntimeError):
    pass


def atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        if path.exists():
            os.fchmod(fd, path.stat().st_mode & 0o7777)      # keep the replaced file's permissions
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        # Persist the directory entry as well as the file content on supported hosts.
        if os.name == "posix":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def backup_path(path: Path) -> Path:
    return Path(path).with_name(Path(path).name + ".bak")


def write_with_backup(path: Path, text: str, valid: Callable[[str], object] | None = None) -> None:
    """Keep the previous complete version as <name>.bak, then replace the primary atomically.
    ``valid`` (a parser) decides whether the current primary is worth keeping as the backup;
    a damaged primary never overwrites a good backup."""
    path = Path(path)
    if path.exists():
        try:
            current = path.read_text()
        except OSError:
            current = None                                   # unreadable primary: keep the backup as is
        keep = current is not None and current != text
        if keep and valid is not None:
            try:
                valid(current)
            except Exception:
                keep = False                                 # damaged/invalid primary never becomes the backup
        if keep:
            atomic_write(backup_path(path), current)         # a failure here propagates: primary untouched
    atomic_write(path, text)


def read_with_backup(path: Path, parse: Callable[[str], T], what: str) -> tuple[T, str | None]:
    """(value, notice). The notice is set when the backup had to be used; the damaged primary is
    kept beside it as <name>.damaged-<time> for evidence before anything rewrites it."""
    path = Path(path)
    # Any failure to read or validate (wrong shapes raise TypeError/AttributeError/KeyError too)
    # means the file is unusable; parsers are pure, so catching broadly is safe here.
    try:
        return parse(path.read_text()), None
    except Exception as primary_error:
        backup = backup_path(path)
        try:
            value = parse(backup.read_text())
            if path.exists():
                kept = path.with_name(f"{path.name}.damaged-{int(time.time())}")
                atomic_write(kept, path.read_bytes().decode("utf-8", "replace"))
        except Exception:
            raise StateRecoveryError(
                f"{what} ({path.name}) could not be read and has no usable backup ({type(primary_error).__name__}). "
                f"Keep the data directory as it is and restore {path.name} from a known-good copy; "
                "nothing was replaced with defaults.") from primary_error
        return value, (f"{what} could not be read ({path.name} damaged, e.g. by a power cut during a save); "
                       f"the previous saved copy was restored. Review it before continuing.")
