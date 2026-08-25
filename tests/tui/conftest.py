"""TUI testleri: offline mock transport handler + app fabrikasi.

Tum testler canli backend gerektirmez — httpx ``MockTransport`` ve Textual
``run_test`` (headless) ile tamamen offline (tasarim §8).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from florence import AsyncFlorenceClient, MemoryTokenStore
from florence.cli.config_cli import CliConfig
from florence.tui.app import FlorenceTUI

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"

try:
    from zoneinfo import ZoneInfo

    _TR_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    _TR_TZ = timezone(timedelta(hours=3))

#: next_open_at BUGUNE gore dinamik uretilir (Istanbul saati 10:00).
_NEXT_OPEN_AT = (
    datetime.now(_TR_TZ)
    .replace(hour=10, minute=0, second=0, microsecond=0)
    + timedelta(days=1)
).isoformat()

#: Test yanit sekilleri (docs/tui-design.md Ek A'daki sozlesmeler birebir).
MOCK_STATUS_OPEN = {"open": True, "next_open_at": _NEXT_OPEN_AT, "holiday": False}
MOCK_STATUS_CLOSED = {"open": False, "next_open_at": _NEXT_OPEN_AT, "holiday": False}
MOCK_STATS_TOP = [
    {"ticker": "THYAO", "total": 99},
    {"ticker": "ASELS", "total": 87},
    {"ticker": "GARAN", "total": 71},
]
MOCK_POPULAR = [
    {"ticker": "THYAO", "name": "Türk Hava Yolları", "last_price": 313.4, "change_pct": 0.93, "volume": 1250000000.0},
    {"ticker": "ASELS", "name": "Aselsan Elektronik", "last_price": 1234.5, "change_pct": 1.2, "volume": 850000000.0},
    {"ticker": "GARAN", "name": "Garanti BBVA", "last_price": 121.5, "change_pct": -2.1, "volume": 650000000.0},
]
MOCK_GAINERS = [
    {"ticker": "THYAO", "last_price": 313.4, "change_pct": 0.93},
    {"ticker": "ASELS", "last_price": 1234.5, "change_pct": 1.2},
]
MOCK_LOSERS = [
    {"ticker": "GARAN", "last_price": 121.5, "change_pct": -2.1},
    {"ticker": "ISCTR", "last_price": 14.3, "change_pct": -0.4},
]
MOCK_GOLD = [
    {"Type": "Gram Altın", "Buying": "40,25", "Selling": "40,75"},
    {"Type": "Çeyrek Altın", "Buying": "3.450,00", "Selling": "3.520,00"},
    {"Type": "Cumhuriyet Altını", "Buying": "13.800,00", "Selling": "14.000,00"},
]
MOCK_CURRENCY = {"USD": {"buying": "42,10"}, "EUR": {"buying": "45,30"}}

#: PART 2 mock'lari (docs/tui-design.md Ek A sozlesmeleri birebir).
MOCK_FAVORITES = ["THYAO", "ASELS"]
MOCK_COMPANY_INFO = {
    "THYAO": {"ticker": "THYAO", "longName": "Türk Hava Yolları", "sector": "Havacılık"},
    "ASELS": {"ticker": "ASELS", "longName": "Aselsan Elektronik", "sector": "Savunma"},
}
MOCK_PRICES = {
    "THYAO": {"ticker": "THYAO", "price": 313.4, "change_pct": 0.93, "market_status": "open"},
    "ASELS": {"ticker": "ASELS", "price": 1234.5, "change_pct": -1.2, "market_status": "open"},
}
MOCK_HISTORY = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 300.0, "close": 310.0, "volume": 1000},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 310.0, "close": 313.4, "volume": 1200},
    {"ts": "2026-07-03T00:00:00+00:00", "open": 313.4, "close": 312.0, "volume": 900},
]
MOCK_NEWS = [
    {"title": "THYAO haberi", "url": "https://example.com/thyao-1"},
    {"title": "THYAO ikinci haber", "url": "https://example.com/thyao-2"},
]

#: PORTFÖY mock'lari (Faz E — P7; alan adlari kod okumasi + helpers-design.md
#: H5 mock şemasından — canli backend bu makinede kalkik olmadigindan
#: docstring'de not dusulur; uydurma alan yok).
MOCK_PORTFOLIOS = [
    {"id": 7, "name": "Benim Portföyüm", "initial_balance": 100000.0},
    {"id": 9, "name": "Uzun Vade", "initial_balance": 50000.0},
]
#: GET /portfolios/{id}/snapshot — birlesik ozet (H5 sözlesmesi).
MOCK_PORTFOLIO_SNAPSHOT = {
    "portfolio_id": 7,
    "total_value": 152340.5,
    "pnl": 12340.5,
    "pnl_pct": 8.8,
}
#: GET /portfolios/{id}/history — varsayilan sekil: deger serisi (OHLC yok).
MOCK_PORTFOLIO_HISTORY = [
    {"ts": "2026-07-01T00:00:00+00:00", "value": 140000.0},
    {"ts": "2026-07-02T00:00:00+00:00", "value": 148000.0},
    {"ts": "2026-07-03T00:00:00+00:00", "value": 152340.5},
]
#: Tam OHLC sekli (T-E3: birebir korunur, sentez yok).
MOCK_PORTFOLIO_HISTORY_OHLC = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 138000.0, "high": 145000.0, "low": 137000.0, "close": 140000.0},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 140000.0, "high": 149000.0, "low": 139500.0, "close": 148000.0},
    {"ts": "2026-07-03T00:00:00+00:00", "open": 148000.0, "high": 153000.0, "low": 147500.0, "close": 152340.5},
]
#: GET /portfolios/{id}/performers — {top: [...], bottom: [...]} (H5).
MOCK_PORTFOLIO_PERFORMERS = {
    "top": [
        {"ticker": "THYAO", "return_pct": 8.8, "pnl": 8400.0},
        {"ticker": "ASELS", "return_pct": 4.2, "pnl": 3200.0},
    ]
}


def make_handler(
    *,
    status_json: dict[str, Any] | None = None,
    status_open: bool = True,
    stats_top: list[dict[str, Any]] | None = None,
    gainers: list[dict[str, Any]] | None = None,
    losers: list[dict[str, Any]] | None = None,
    popular: list[dict[str, Any]] | None = None,
    gold: list[dict[str, Any]] | None = None,
    currency: dict[str, Any] | None = None,
    rate_limit_path: str | None = None,
    retry_after: str = "30",
    favorites: list[str] | None = None,
    favorites_summary: list[dict[str, Any]] | None = None,
    prices: dict[str, dict[str, Any]] | None = None,
    price_fail_tickers: set[str] | None = None,
    company_info: dict[str, dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
    news: list[dict[str, Any]] | None = None,
    portfolios: list[dict[str, Any]] | None = None,
    portfolio_snapshot: dict[str, Any] | None = None,
    portfolio_fail_snapshot: bool = False,
    portfolio_history: list[dict[str, Any]] | None = None,
    portfolio_performers: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Path'e gore mock yanit donduren httpx handler (tamamen offline).

    ``rate_limit_path`` verilirse o path 429 + Retry-After doner; diger
    uclar normal. ``None`` listeler bos yanit anlamina gelir (bos durum
    testleri icin), ``[]`` ise gercekten bos liste doner. PART 2 uclari:
    ``/favorites``, ``/price/current`` (ticker'a gore), ``/price/history/``,
    ``/companies/info/``, ``/news/`` — ``price_fail_tickers`` icindeki
    ticker'larin fiyati 500 doner (kismi hata toleransi testi). Faz E
    portfoy uclari: ``/portfolios`` (liste), ``/portfolios/{id}/snapshot``,
    ``/portfolios/{id}/history``, ``/portfolios/{id}/performers`` —
    ``portfolio_fail_snapshot`` snapshot ucuna 500 doner (kismi hata testi).
    """
    status = (
        status_json
        if status_json is not None
        else (MOCK_STATUS_OPEN if status_open else MOCK_STATUS_CLOSED)
    )
    price_map = MOCK_PRICES if prices is None else prices
    info_map = MOCK_COMPANY_INFO if company_info is None else company_info

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
            tickers_param = request.url.params.get("tickers")
            if tickers_param:
                if favorites_summary is not None:
                    return httpx.Response(200, json=favorites_summary)
                fav_list = [t.strip() for t in tickers_param.split(",") if t.strip()]
                all_stocks = (
                    (popular if popular is not None else MOCK_POPULAR)
                    + (gainers if gainers is not None else MOCK_GAINERS)
                    + (losers if losers is not None else MOCK_LOSERS)
                )
                stock_map = {s["ticker"]: s for s in all_stocks}
                return httpx.Response(
                    200,
                    json=[
                        stock_map.get(
                            t,
                            {"ticker": t, "name": t, "last_price": 100.0, "change_pct": 0.0},
                        )
                        for t in fav_list
                    ],
                )
            if sort == "gainers":
                rows = MOCK_GAINERS if gainers is None else gainers
            elif sort == "losers":
                rows = MOCK_LOSERS if losers is None else losers
            elif sort == "popular":
                rows = MOCK_POPULAR if popular is None else popular
            else:
                rows = MOCK_POPULAR if popular is None else popular
            return httpx.Response(200, json=rows)
        if "/companies/info/" in path:
            ticker = path.rstrip("/").split("/")[-1]
            entry = info_map.get(ticker)
            if entry is None:
                return httpx.Response(404, json={"detail": "unknown_ticker"})
            return httpx.Response(200, json=entry)
        if path.endswith("/economy/gold-prices"):
            rows = MOCK_GOLD if gold is None else gold
            return httpx.Response(200, json=rows)
        if path.endswith("/economy/currency"):
            data = MOCK_CURRENCY if currency is None else currency
            return httpx.Response(200, json=data)
        if path.endswith("/favorites"):
            rows = MOCK_FAVORITES if favorites is None else favorites
            return httpx.Response(200, json=rows)
        # Faz E portfoy uclari (P7).
        if path.endswith("/portfolios"):
            rows = MOCK_PORTFOLIOS if portfolios is None else portfolios
            return httpx.Response(200, json=rows)
        if "/portfolios/" in path and path.endswith("/snapshot"):
            if portfolio_fail_snapshot:
                return httpx.Response(500, json={"detail": "error_internal"})
            data = MOCK_PORTFOLIO_SNAPSHOT if portfolio_snapshot is None else portfolio_snapshot
            return httpx.Response(200, json=data)
        if "/portfolios/" in path and path.endswith("/history"):
            rows = MOCK_PORTFOLIO_HISTORY if portfolio_history is None else portfolio_history
            return httpx.Response(200, json=rows)
        if "/portfolios/" in path and path.endswith("/performers"):
            data = MOCK_PORTFOLIO_PERFORMERS if portfolio_performers is None else portfolio_performers
            return httpx.Response(200, json=data)
        if path.endswith("/price/current"):
            ticker = request.url.params.get("ticker", "")
            if price_fail_tickers and ticker in price_fail_tickers:
                return httpx.Response(500, json={"detail": "error_internal"})
            entry = price_map.get(ticker)
            if entry is None:
                return httpx.Response(404, json={"detail": "unknown_ticker"})
            return httpx.Response(200, json=entry)
        if "/price/history/" in path:
            rows = MOCK_HISTORY if history is None else history
            return httpx.Response(200, json=rows)
        if "/news/" in path:
            rows = MOCK_NEWS if news is None else news
            return httpx.Response(200, json=rows)
        if path.endswith("/digest"):
            return httpx.Response(
                200,
                json={
                    "title": "Günün Piyasa Özeti",
                    "date": "2026-08-25",
                    "slot": "morning",
                    "content": "BIST 100 güne pozitif başlangıç yaptı.",
                    "sections": [
                        {
                            "heading": "Öne Çıkan Gelişmeler",
                            "body": "Havacılık ve teknoloji hisselerinde güçlü alımlar izlendi.",
                        }
                    ],
                },
            )
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
