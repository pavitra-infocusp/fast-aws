"""Async boto3 executor with caching, SSO login, and readonly enforcement."""

from __future__ import annotations

import asyncio
import os
import shutil
import threading
import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import (
    ClientError,
    SSOError,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
    UnknownTokenProviderError,
)

from fast_aws.auth import make_session

SSO_AUTH_CODES = {
    "ExpiredTokenException",
    "ExpiredToken",
    "UnauthorizedException",
    "InvalidToken",
    "TokenRefreshRequired",
}

SSO_TOKEN_ERRORS = (
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
    SSOTokenLoadError,
    SSOError,
    UnknownTokenProviderError,
)


class AuthError(Exception):
    """Raised for problems with AWS credentials / SSO login."""


class LoginRequired(Exception):
    """Raised when a call failed because an SSO login is needed."""


class ReadonlyViolation(Exception):
    """Raised when a mutating call is attempted in readonly mode."""


def is_auth_error(exc: Exception) -> bool:
    if isinstance(exc, SSO_TOKEN_ERRORS):
        return True
    if isinstance(exc, ClientError):
        code = (exc.response.get("Error") or {}).get("Code") or ""
        return code in SSO_AUTH_CODES
    return False


class Executor:
    """Runs boto3 calls off the event loop with a small TTL cache.

    Raises LoginRequired when an SSO token is missing/expired so the UI can
    show an interactive login screen and retry.
    """

    def __init__(self, profile: str | None, region: str, readonly: bool = True, ttl: float = 30.0):
        self.profile = profile
        self.region = region
        self.readonly = readonly
        self.ttl = ttl
        self._session: Any = None
        self._clients: dict[str, Any] = {}
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    # -- identity ----------------------------------------------------------
    @property
    def mode_label(self) -> str:
        return "READONLY" if self.readonly else "EDIT"

    def set_readonly(self, value: bool) -> None:
        self.readonly = value

    def bust(self) -> None:
        with self._lock:
            self._cache.clear()

    # -- low level ---------------------------------------------------------
    def _get_client(self, service: str) -> Any:
        with self._lock:
            if self._session is None:
                self._session = make_session(self.profile, self.region)
            if service not in self._clients:
                self._clients[service] = self._session.client(service)
            return self._clients[service]

    async def call(
        self,
        service: str,
        fn: str,
        *args: Any,
        ttl: float | bool | None = None,
        no_cache: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Run a boto3 client method in a thread, cached by default."""
        ttl_secs = self.ttl if ttl is None else ttl
        key = (self.profile, self.region, service, fn, repr(args), repr(kwargs))
        if not no_cache and ttl_secs is not False:
            with self._lock:
                hit = self._cache.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]

        try:
            result = await asyncio.to_thread(self._run_sync, service, fn, args, kwargs)
        except SSO_TOKEN_ERRORS as exc:
            raise LoginRequired from exc
        except ClientError as exc:
            if not is_auth_error(exc):
                raise
            raise LoginRequired from exc

        if ttl_secs is not False:
            with self._lock:
                self._cache[key] = (time.monotonic() + (ttl_secs or 0), result)
        return result

    def _run_sync(self, service: str, fn: str, args: tuple, kwargs: dict) -> Any:
        return getattr(self._get_client(service), fn)(*args, **kwargs)

    # -- readonly enforcement ---------------------------------------------
    def ensure_can_mutate(self) -> None:
        if self.readonly:
            raise ReadonlyViolation(
                "Readonly mode: press Ctrl+E to enable Edit mode (or launch with --edit)"
            )

    # -- SSO ---------------------------------------------------------------
    async def sso_login_stream(self, on_line: Callable[[str], None]) -> str:
        """Run `aws sso login` streaming its output (URL etc.) to on_line."""
        exe = shutil.which("aws")
        if not exe:
            raise AuthError("aws CLI not found on PATH — required for SSO login")
        env = dict(os.environ)
        env["AWS_PAGER"] = ""
        proc = await asyncio.create_subprocess_exec(
            exe,
            "sso",
            "login",
            "--profile",
            self.profile or "default",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        assert proc.stdout is not None
        lines: list[str] = []
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode(errors="replace").rstrip()
            lines.append(line)
            on_line(line)
        code = await proc.wait()
        if code != 0:
            raise AuthError(f"SSO login failed (exit {code})")
        with self._lock:
            self._clients.clear()
            self._session = None
            self._cache.clear()
        return "\n".join(lines)
