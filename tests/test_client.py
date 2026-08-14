"""Client testleri: 401 otomatik refresh, 429 Retry-After, 5xx retry,
NetworkError, raw cikti, bos gövde. TAMAMEN OFFLINE (MockTransport)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from florence import (
    AsyncFlorenceClient,
    AuthError,
    FlorenceAPIError,
    FlorenceClient,
    MemoryTokenStore,
    NetworkError,
    RateLimitError,
)

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"


def _pair(access: str, refresh: str) -> dict:
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


# ----------------------------------------------------------------------
# 401 -> otomatik refresh -> yeniden dene (senkron)
# ----------------------------------------------------------------------
def test_401_auto_refresh_sync():
    store = MemoryTokenStore()
    store.set_tokens("bayat-at", "rt-1")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/auth/refresh"):
            return httpx.Response(200, json=_pair("taze-at", "rt-2"))
        if request.headers.get("Authorization") == "Bearer bayat-at":
            return httpx.Response(401, json={"detail": "Invalid or expired token"})
        return httpx.Response(200, json={"credits": 12.5})

    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler), max_retries=0)
    result = client.request("GET", f"{P}/credits")

    assert result == {"credits": 12.5}
    assert store.get_access_token() == "taze-at"
    # 1 profil istegi (bayat) + 1 refresh + 1 profil istegi (taze)
    assert len(calls) == 3


def test_401_auto_refresh_failure_raises_auth_error():
    store = MemoryTokenStore()
    store.set_tokens("bayat-at", "bayat-rt")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/refresh"):
            return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})
        return httpx.Response(401, json={"detail": "Invalid or expired token"})

    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler), max_retries=0)
    with pytest.raises(AuthError):
        client.request("GET", f"{P}/credits")


def test_401_without_refresh_token_raises_auth_error():
    client = FlorenceClient(token_store=MemoryTokenStore(), transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"detail": "Invalid or expired token"})
    ), max_retries=0)
    with pytest.raises(AuthError):
        client.request("GET", f"{P}/credits")


# ----------------------------------------------------------------------
# 429 / 5xx retry (senkron)
# ----------------------------------------------------------------------
def test_429_retry_after_respected_sync(monkeypatch):
    """429 + Retry-After: 0 -> beklenir, sonra basari."""
    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    slept: list[float] = []
    monkeypatch.setattr("florence.client.time.sleep", lambda s: slept.append(s))
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"detail": "Too many requests"})
        return httpx.Response(200, json={"status": "ok"})

    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler), max_retries=2)
    result = client.request("GET", f"{P}/market/status")
    assert result == {"status": "ok"}
    assert state["n"] == 2
    assert slept == [0.0]  # Retry-After'a saygi


def test_429_exhausts_retries_raises_rate_limit():
    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"detail": "Too many requests"})

    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler), max_retries=1)
    with pytest.raises(RateLimitError):
        client.request("GET", f"{P}/market/status")
    assert state["n"] == 2  # 1 ilk deneme + 1 retry (max_retries=1)


def test_5xx_retry_then_success():
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(503, json={"detail": "Database busy, please retry"})
        return httpx.Response(200, json={"status": "ok"})

    client = FlorenceClient(transport=httpx.MockTransport(handler), max_retries=2)
    result = client.request("GET", f"{P}/market/status")
    assert result == {"status": "ok"}
    assert state["n"] == 2


def test_500_after_all_retries_raises_florence_api_error():
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        return httpx.Response(500, json={"detail": "Database error"})

    client = FlorenceClient(transport=httpx.MockTransport(handler), max_retries=2)
    with pytest.raises(FlorenceAPIError) as exc:
        client.request("GET", f"{P}/market/status")
    assert exc.value.status_code == 500
    assert state["n"] == 3


def test_retry_disabled_with_retry_false():
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        return httpx.Response(500, json={"detail": "Database error"})

    client = FlorenceClient(transport=httpx.MockTransport(handler), max_retries=2)
    with pytest.raises(FlorenceAPIError):
        client.request("GET", f"{P}/market/status", retry=False)
    assert state["n"] == 1


# ----------------------------------------------------------------------
# NetworkError
# ----------------------------------------------------------------------
def test_connection_error_maps_to_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("baglanti kurulamadi", request=request)

    client = FlorenceClient(transport=httpx.MockTransport(handler), max_retries=0)
    with pytest.raises(NetworkError):
        client.request("GET", f"{P}/market/status")


def test_connection_error_retried_then_network_error():
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        raise httpx.ConnectError("baglanti kurulamadi", request=request)

    client = FlorenceClient(transport=httpx.MockTransport(handler), max_retries=2)
    with pytest.raises(NetworkError):
        client.request("GET", f"{P}/market/status")
    assert state["n"] == 3


# ----------------------------------------------------------------------
# Cikti normalizasyonu
# ----------------------------------------------------------------------
def test_empty_body_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = FlorenceClient(transport=httpx.MockTransport(handler))
    assert client.request("GET", f"{P}/x") is None


def test_non_json_body_returns_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="plain text")

    client = FlorenceClient(transport=httpx.MockTransport(handler))
    assert client.request("GET", f"{P}/x") == "plain text"


def test_raw_response_mode():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x1f\x8b-binary", headers={"Content-Type": "application/gzip"})

    client = FlorenceClient(transport=httpx.MockTransport(handler))
    resp = client.request("GET", f"{P}/data/export/download/tok", raw=True)
    assert isinstance(resp, httpx.Response)
    assert resp.content == b"\x1f\x8b-binary"


# ----------------------------------------------------------------------
# Asenkron client
# ----------------------------------------------------------------------
def test_async_401_auto_refresh():
    store = MemoryTokenStore()
    store.set_tokens("bayat-at", "rt-1")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/refresh"):
            calls.append("refresh")
            return httpx.Response(200, json=_pair("taze-at", "rt-2"))
        calls.append(request.headers.get("Authorization", "none"))
        if request.headers.get("Authorization") == "Bearer bayat-at":
            return httpx.Response(401, json={"detail": "Invalid or expired token"})
        return httpx.Response(200, json={"credits": 5.0})

    async def run() -> None:
        async with AsyncFlorenceClient(
            token_store=store, transport=httpx.MockTransport(handler), max_retries=0
        ) as client:
            result = await client.request("GET", f"{P}/credits")
            assert result == {"credits": 5.0}

    asyncio.run(run())
    assert calls == ["Bearer bayat-at", "refresh", "Bearer taze-at"]


def test_async_429_retry_after(monkeypatch):
    slept: list[float] = []
    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr("florence.client.asyncio.sleep", fake_sleep)
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"detail": "Too many requests"})
        return httpx.Response(200, json={"status": "ok"})

    async def run() -> None:
        async with AsyncFlorenceClient(
            transport=httpx.MockTransport(handler), max_retries=2
        ) as client:
            result = await client.request("GET", f"{P}/market/status")
            assert result == {"status": "ok"}

    asyncio.run(run())
    assert state["n"] == 2
    assert slept == [0.0]


def test_async_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("baglanti kurulamadi", request=request)

    async def run() -> None:
        async with AsyncFlorenceClient(
            transport=httpx.MockTransport(handler), max_retries=0
        ) as client:
            with pytest.raises(NetworkError):
                await client.request("GET", f"{P}/market/status")

    asyncio.run(run())
