"""Local owner/agent credentials. These are capabilities, not an OS sandbox.

Processes with access to the owner's files can assume the owner's identity.
Never use the audit source header as an authentication mechanism.
"""

from __future__ import annotations

import os
import hashlib
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
import secrets
from typing import Literal

Principal = Literal["owner", "agent"]
COOKIE = "helixtune_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_BROWSER_SESSIONS = 64


class SessionLimit(RuntimeError):
    pass


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
    def __init__(self, data_dir: Path, *, session_ttl: int = SESSION_TTL_SECONDS,
                 max_sessions: int = MAX_BROWSER_SESSIONS, clock: Callable[[], float] = time.monotonic):
        if session_ttl <= 0 or max_sessions <= 0:
            raise ValueError("Session lifetime and capacity must be positive")
        self.session_ttl = session_ttl
        self._max_sessions = max_sessions
        self._clock = clock
        self._session_lock = threading.RLock()
        # Only digests are retained; restarting the server revokes every browser session.
        self._sessions: dict[str, float] = {}
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


    @staticmethod
    def _session_key(value: str) -> str | None:
        # Distinct namespace: neither long-lived role credential is a browser session.
        if not re.fullmatch(r"hs_[A-Za-z0-9_-]{43}", value):
            return None
        return hashlib.sha256(value.encode()).hexdigest()

    def _prune_sessions(self) -> None:
        now = self._clock()
        self._sessions = {key: expiry for key, expiry in self._sessions.items() if expiry > now}

    def start_session(self, owner_token: str, previous: str = "") -> str | None:
        if self.authenticate(owner_token) != "owner":
            return None
        with self._session_lock:
            self._prune_sessions()
            previous_key = self._session_key(previous)
            count = len(self._sessions) - int(previous_key in self._sessions)
            if count >= self._max_sessions:
                raise SessionLimit("Browser session limit reached; sign out another browser or restart the server")
            session_id = "hs_" + secrets.token_urlsafe(32)
            key = self._session_key(session_id)
            # Collision is fantastically unlikely, but never alias another browser.
            while key in self._sessions:
                session_id = "hs_" + secrets.token_urlsafe(32)
                key = self._session_key(session_id)
            if previous_key is not None:
                self._sessions.pop(previous_key, None)
            self._sessions[key] = self._clock() + self.session_ttl
            return session_id

    def authenticate_session(self, session_id: str) -> Principal | None:
        key = self._session_key(session_id)
        if key is None:
            return None
        with self._session_lock:
            self._prune_sessions()
            return "owner" if key in self._sessions else None

    def revoke_session(self, session_id: str) -> None:
        key = self._session_key(session_id)
        with self._session_lock:
            self._sessions.pop(key, None)


def agent_token() -> str:
    explicit = os.environ.get("HELIXTUNE_TOKEN")
    if explicit:
        return explicit
    root = Path(os.environ.get("HELIXTUNE_DATA_DIR", "~/.helixtune")).expanduser()
    return read_token(root, "agent")
