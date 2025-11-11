"""Session management helpers for Canary SAF."""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable, Iterable, Optional

import httpx

logger = logging.getLogger(__name__)


class SAFSessionError(RuntimeError):
    """Raised when SAF session operations fail."""


class SAFSessionManager:
    """Manages SAF session lifecycle (acquire, keepAlive, refresh, revoke)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        client_id: str,
        historians: Iterable[str],
        session_timeout_ms: int,
        keepalive_idle_seconds: int,
        keepalive_jitter_seconds: int,
        http_client: Optional[httpx.Client] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be provided")
        if not api_token:
            raise ValueError("api_token must be provided")

        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._client_id = client_id or "uns-meta-session"
        self._historians = [entry for entry in historians if entry]
        self._session_timeout_ms = max(1000, session_timeout_ms)
        self._keepalive_idle_seconds = max(1, keepalive_idle_seconds)
        self._keepalive_jitter_seconds = max(0, keepalive_jitter_seconds)
        self._clock = clock
        self._client = http_client or httpx.Client(
            timeout=self._session_timeout_ms / 1000 + 5
        )

        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._last_activity = self._clock()
        self._last_keepalive = self._clock()

    # ------------------------------------------------------------------ Public API
    def get_token(self) -> str:
        """Return a session token, acquiring or keeping alive as needed."""

        with self._lock:
            self._ensure_token_locked()
            self._maybe_keep_alive_locked()
            if not self._token:
                raise SAFSessionError("Failed to acquire SAF session token")
            return self._token

    def mark_activity(self) -> None:
        with self._lock:
            self._last_activity = self._clock()

    def invalidate(self) -> None:
        with self._lock:
            self._token = None

    def revoke(self) -> None:
        with self._lock:
            token = self._token
            self._token = None
        if not token:
            return
        try:
            self._client.post(
                f"{self._base_url}/revokeSessionToken",
                json={"sessionToken": token},
            )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to revoke SAF session token", exc_info=True)

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ Internal helpers
    def _ensure_token_locked(self) -> None:
        if self._token:
            return
        payload = {
            "apiToken": self._api_token,
            "clientId": self._client_id,
            "historians": self._historians,
            "settings": {"clientTimeout": self._session_timeout_ms},
        }
        try:
            response = self._client.post(
                f"{self._base_url}/getSessionToken",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise SAFSessionError("SAF getSessionToken request failed") from exc
        data = response.json()
        token = data.get("sessionToken") if isinstance(data, dict) else None
        if not token:
            raise SAFSessionError("SAF getSessionToken response missing sessionToken")
        self._token = token
        now = self._clock()
        self._last_activity = now
        self._last_keepalive = now

    def _maybe_keep_alive_locked(self) -> None:
        if not self._token:
            return
        now = self._clock()
        idle = now - self._last_activity
        if idle < self._keepalive_idle_seconds:
            return
        jitter = random.uniform(0, self._keepalive_jitter_seconds)
        if idle < self._keepalive_idle_seconds + jitter:
            return
        try:
            self._client.post(
                f"{self._base_url}/keepAlive",
                json={"sessionToken": self._token},
            ).raise_for_status()
            self._last_keepalive = now
            self._last_activity = now
            logger.debug("SAF keepAlive sent after %.2f seconds idle", idle)
        except Exception:  # noqa: BLE001
            logger.warning("SAF keepAlive failed", exc_info=True)
            self._token = None

    # Context manager support --------------------------------------------------
    def __enter__(self) -> "SAFSessionManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.revoke()
        finally:
            self.close()

    def __del__(self) -> None:  # pragma: no cover - best effort close
        try:
            self.close()
        except Exception:
            pass
