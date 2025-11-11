from __future__ import annotations

import httpx
import pytest

from uns_metadata_sync.canary.session import SAFSessionError, SAFSessionManager


class ManualClock:
    def __init__(self, start: float = 0.0) -> None:
        self._value = start

    def advance(self, delta: float) -> float:
        self._value += delta
        return self._value

    def __call__(self) -> float:
        return self._value


def test_session_manager_acquire_and_keepalive() -> None:
    clock = ManualClock()
    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        events.append(request.url.path)
        if request.url.path.endswith("/getSessionToken"):
            return httpx.Response(200, json={"result": {"sessionToken": "token-1"}})
        if request.url.path.endswith("/keepAlive"):
            return httpx.Response(200, json={"result": "ok"})
        if request.url.path.endswith("/revokeSessionToken"):
            return httpx.Response(200, json={"result": "ok"})
        pytest.fail(f"unexpected path {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manager = SAFSessionManager(
        base_url="https://example/api/v1",
        api_token="api-token",
        client_id="client-1",
        historians=["hist"],
        session_timeout_ms=120000,
        keepalive_idle_seconds=1,
        keepalive_jitter_seconds=0,
        http_client=client,
        clock=clock,
    )

    token = manager.get_token()
    assert token == "token-1"
    assert events == ["/getSessionToken"]

    clock.advance(2.0)
    token_again = manager.get_token()
    assert token_again == "token-1"
    assert events[-1] == "/keepAlive"

    manager.mark_activity()
    manager.revoke()
    manager.close()


def test_session_manager_reacquires_after_keepalive_failure() -> None:
    clock = ManualClock()
    calls: list[str] = []
    keepalive_fail = True

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal keepalive_fail
        calls.append(request.url.path)
        if request.url.path.endswith("/getSessionToken"):
            token_value = "token-2" if keepalive_fail is False else "token-1"
            return httpx.Response(200, json={"result": {"sessionToken": token_value}})
        if request.url.path.endswith("/keepAlive"):
            keepalive_fail = False
            return httpx.Response(500, json={"error": "BadSessionToken"})
        pytest.fail(f"unexpected path {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manager = SAFSessionManager(
        base_url="https://example/api/v1",
        api_token="api-token",
        client_id="client-1",
        historians=[],
        session_timeout_ms=120000,
        keepalive_idle_seconds=1,
        keepalive_jitter_seconds=0,
        http_client=client,
        clock=clock,
    )

    assert manager.get_token() == "token-1"
    clock.advance(2.0)
    # KeepAlive failure invalidates token
    with pytest.raises(SAFSessionError):
        manager.get_token()
    assert calls[-1] == "/keepAlive"

    # Next acquisition should call getSessionToken again
    assert manager.get_token() == "token-2"
    manager.close()
