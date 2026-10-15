"""Local owner/agent credentials. These are capabilities, not an OS sandbox.

Processes with access to the owner's files can assume the owner's identity.
Never use the audit source header as an authentication mechanism.
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
from typing import Literal

Principal = Literal["owner", "agent"]
COOKIE = "helixtune_session"


def token_path(data_dir: Path, principal: Principal) -> Path:
    return data_dir / "auth" / f"{principal}.token"


def read_token(data_dir: Path, principal: Principal) -> str:
    try:
        token = token_path(data_dir, principal).read_text().strip()
    except FileNotFoundError:
        raise RuntimeError("Access credentials are missing; start helixtune serve with this data directory first") from None
    if len(token) < 32:
        raise RuntimeError("Invalid access credential file")
    return token


class AccessControl:
    def __init__(self, data_dir: Path):
        directory = data_dir / "auth"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self._tokens: dict[Principal, str] = {}
        for principal in ("owner", "agent"):
            path = token_path(data_dir, principal)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w") as fh:
                    fh.write(secrets.token_urlsafe(32) + "\n")
            path.chmod(0o600)
            self._tokens[principal] = read_token(data_dir, principal)
        if secrets.compare_digest(self._tokens["owner"], self._tokens["agent"]):
            raise RuntimeError("Owner and agent credentials must be different")

    def token(self, principal: Principal) -> str:
        return self._tokens[principal]

    def authenticate(self, token: str) -> Principal | None:
        for principal, expected in self._tokens.items():
            if secrets.compare_digest(token.encode(), expected.encode()):
                return principal
        return None


def agent_token() -> str:
    explicit = os.environ.get("HELIXTUNE_TOKEN")
    if explicit:
        return explicit
    root = Path(os.environ.get("HELIXTUNE_DATA_DIR", "~/.helixtune")).expanduser()
    return read_token(root, "agent")
