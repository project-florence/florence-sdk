"""TUI testleri: offline mock transport handler + app fabrikasi.

Tum testler canli backend gerektirmez — httpx ``MockTransport`` ve Textual
``run_test`` (headless) ile tamamen offline (tasarim §8).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from florence import AsyncFlorenceClient, MemoryTokenStore
from florence.cli.config_cli import CliConfig
from florence.tui.app import FlorenceTUI

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"

#: Test yanit sekilleri (docs/tui-design.md Ek A'daki sozlesmeler birebir).
MOCK_STATUS_OPEN = {"open": True, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False}
MOCK_STATUS_CLOSED = {"open": False, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False}
MOCK_STATS_TOP = [
    {"ticker": "THYAO", "count": 99},
    {"ticker": "ASELS", "count": 87},
    {"ticker": "GARAN", "count": 71},
]
MOCK_GAINERS = [
    {"ticker": "THYAO", "price": 313.4, "change_pct": 0.93},
    {"ticker": "ASELS", "price": 1234.5, "change_pct": 1.2},
]
MOCK_LOSERS = [
    {"ticker": "GARAN", "price": 121.5, "change_pct": -2.1},
    {"ticker": "ISCTR", "price": 14.3, "change_pct": -0.4},
]
MOCK_GOLD = [
    {"Type": "Gram Altın", "Buying": "40,25", "Selling": "40,75"},
    {"Type": "Çeyrek Altın", "Buying": "3.450,00", "Selling": "3.520,00"},
    {"Type": "Cumhuriyet Altını", "Buying": "13.800,00", "Selling": "14.000,00"},
]
MOCK_CURRENCY = {"USD": {"buying": "42,10"}, "EUR": {"buying": "45,30"}}


def make_handler(
    *,
    status_json: dict[str, Any] | None = None,
    status_open: bool = True,
    stats_top: list[dict[str, Any]] | None = None,
    gainers: list[dict[str, Any]] | None = None,
    losers: list[dict[str, Any]] | None = None,
    gold: list[dict[str, Any]] | None = None,
    currency: dict[str, Any] | None = None,
    rate_limit_path: str | None = None,
    retry_after: str = "30",
) -> Callable[[httpx.Request], httpx.Response]:
    """Path'e gore mock yanit donduren httpx handler (tamamen offline).

    ``rate_limit_path`` verilirse o path 429 + Retry-After doner; diger
    uclar normal. ``None`` listeler bos yanit anlamina gelir (boş durum
    testleri icin), ``[]`` ise gercekten bos liste doner.
    """
    status = (
        status_json
        if status_json is not None
        else (MOCK_STATUS_OPEN if status_open else MOCK_STATUS_CLOSED)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if rate_limit_path and path.endswith(rate_limit_path):
            return httpx.Response(
                429,
                json={"detail": "error_rate_limited"},
                headers={"Retry-After": retry_after},
            )
        if path.endswith("/market/status"):
            return httpx.Response(200, json=status)
        if path.endswith("/stats/top"):
            rows = MOCK_STATS_TOP if stats_top is None else stats_top
            return httpx.Response(200, json=rows)
        if path.endswith("/companies/summary"):
            sort = request.url.params.get("sort", "popular")
            if sort == "gainers":
                rows = MOCK_GAINERS if gainers is None else gainers
            elif sort == "losers":
                rows = MOCK_LOSERS if losers is None else losers
            else:
                rows = []
            return httpx.Response(200, json=rows)
        if path.endswith("/economy/gold-prices"):
            rows = MOCK_GOLD if gold is None else gold
            return httpx.Response(200, json=rows)
        if path.endswith("/economy/currency"):
            data = MOCK_CURRENCY if currency is None else currency
            return httpx.Response(200, json=data)
        return httpx.Response(404, json={"detail": "unmocked"})

    return handler


@pytest.fixture
def handler_factory() -> Callable[..., Callable[[httpx.Request], httpx.Response]]:
    return make_handler


@pytest.fixture
def make_client(
    handler_factory: Callable[..., Callable[[httpx.Request], httpx.Response]],
) -> Callable[..., AsyncFlorenceClient]:
    def _client(
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        authenticated: bool = True,
        max_retries: int = 0,
    ) -> AsyncFlorenceClient:
        store = MemoryTokenStore()
        if authenticated:
            store.set_tokens("at-1", "rt-1")
        # max_retries=0: 429/5xx aninda hata nesnesine doner (test hizi).
        return AsyncFlorenceClient(
            transport=httpx.MockTransport(handler),
            token_store=store,
            max_retries=max_retries,
        )

    return _client


@pytest.fixture
def make_app(
    tmp_path: Any,
    make_client: Callable[..., AsyncFlorenceClient],
) -> Callable[..., FlorenceTUI]:
    def _app(
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        authenticated: bool = True,
        refresh_seconds: float = 0.05,
        **tui_kwargs: Any,
    ) -> FlorenceTUI:
        client = make_client(handler, authenticated=authenticated)
        # Gercek kullanici config'ine dokunmamak icin tmp config yolu.
        cfg = CliConfig(path=tmp_path / "config.toml")
        return FlorenceTUI(
            client=client,
            config=cfg,
            refresh_seconds=refresh_seconds,
            **tui_kwargs,
        )

    return _app


async def wait_for(app: FlorenceTUI, predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    """Headless testlerde kosul saglanana kadar event loop'u pompalar."""
    import asyncio
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("zaman asimi: kosul saglanamadi")
