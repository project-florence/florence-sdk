"""Smoke ve import testleri: paket kurulumu, public API yuzeyi, context manager'lar."""

from __future__ import annotations

import asyncio

import httpx
import respx

import florence
from florence import (
    AsyncFlorenceClient,
    FlorenceClient,
    MemoryTokenStore,
    TokenPair,
)

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"


def test_import_and_version():
    assert florence.__version__ == "0.3.0"
    assert hasattr(florence, "FlorenceClient")
    assert hasattr(florence, "AsyncFlorenceClient")
    assert hasattr(florence, "AuthManager")
    assert hasattr(florence, "RateLimitError")
    assert hasattr(florence, "TokenPair")


def test_smoke_client_setup():
    """Import + kurulum calisiyor (istege bagli olmayan endpoint yok)."""
    client = FlorenceClient(base_url="http://localhost:7055", token_store=MemoryTokenStore())
    assert client.base_url == "http://localhost:7055"
    assert client.auth.access_token() is None
    # Resource katmani kuruldu:
    assert client.market is not None
    assert client.portfolio is not None
    assert client.analysis is not None
    assert client.export is not None
    assert client.auth_res is not None
    assert client.user is not None
    assert client.economy is not None
    assert client.bots is not None
    assert client.misc is not None
    client.close()


def test_client_context_manager_sync():
    with respx.mock:
        respx.post(f"{P}/auth/login").mock(
            return_value=httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "token_type": "bearer"})
        )
        with FlorenceClient(token_store=MemoryTokenStore()) as client:
            pair = client.login("kullanici", "sifre12345")
            assert isinstance(pair, TokenPair)


def test_async_client_context_manager():
    with respx.mock:
        respx.post(f"{P}/auth/login").mock(
            return_value=httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "token_type": "bearer"})
        )

        async def run() -> None:
            async with AsyncFlorenceClient(token_store=MemoryTokenStore()) as client:
                pair = await client.login_async("kullanici", "sifre12345")
                assert pair.access_token == "at"

        asyncio.run(run())


def test_login_shortcut_and_refresh_shortcut():
    store = MemoryTokenStore()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1", "token_type": "bearer"})
        if request.url.path.endswith("/auth/refresh"):
            return httpx.Response(200, json={"access_token": "at-2", "refresh_token": "rt-2", "token_type": "bearer"})
        return httpx.Response(404, json={"detail": "unmocked"})

    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    assert client.login("kullanici", "sifre12345").access_token == "at-1"
    assert client.auth.refresh().access_token == "at-2"
    client.close()
