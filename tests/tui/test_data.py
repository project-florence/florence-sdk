"""DataHub birim testleri (TAMAMEN OFFLINE): cache, 429, K4 planlama, formatlar.

Tasarim §8.2: cache TTL, 429 interval uzatmasi, piyasa kapali planlamasi,
TR donusumler — UI'siz dogrudan ``DataHub`` uzerinden test edilir.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from florence import AsyncFlorenceClient, MemoryTokenStore, RateLimitError
from florence.tui.data import (
    AUTH_REQUIRED_SECTIONS,
    DataHub,
    delta_style,
    error_message,
    gold_summary,
    tr_delta,
    tr_number,
)

from .conftest import MOCK_STATUS_OPEN, make_handler


def _hub(handler, **kwargs) -> DataHub:
    client = AsyncFlorenceClient(
        transport=httpx.MockTransport(handler),
        token_store=MemoryTokenStore(),
        max_retries=0,
    )
    return DataHub(client=client, **kwargs)


# ----------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------
def test_cache_serves_second_call_without_network():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path.endswith("/stats/top"):
            return httpx.Response(200, json=[{"ticker": "THYAO", "count": 99}])
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        hub = _hub(handler)
        first = await hub.get_stats_top(limit=5)
        second = await hub.get_stats_top(limit=5)
        assert first == second == [{"ticker": "THYAO", "count": 99}]
        assert calls["n"] == 1  # ikinci cagri cache'ten — ag istegi yok

    asyncio.run(run())


def test_cache_expires_after_ttl():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path.endswith("/stats/top"):
            return httpx.Response(200, json=[{"ticker": "THYAO", "count": 99}])
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        # ttl_overrides ile TTL kucultulur — 10dk beklenmez (tasarim §8.3).
        hub = _hub(handler, ttl_overrides={"stats_top": 0.05})
        await hub.get_stats_top(limit=5)
        await asyncio.sleep(0.07)
        await hub.get_stats_top(limit=5)
        assert calls["n"] == 2

    asyncio.run(run())


def test_last_update_set_on_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stats/top"):
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        hub = _hub(handler)
        assert hub.last_update is None
        await hub.get_stats_top(limit=5)
        assert hub.last_update is not None

    asyncio.run(run())


# ----------------------------------------------------------------------
# Rate limit (§4.4)
# ----------------------------------------------------------------------
def test_rate_limit_extends_interval():
    hub = _hub(make_handler())
    hub.register_rate_limit(30)
    # max(45*2, 30+10) = 90
    assert hub.next_poll_delay() == 90
    # 3 basarili tick sonrasi normale doner
    hub.register_success()
    hub.register_success()
    hub.register_success()
    assert hub.next_poll_delay() == 45


def test_rate_limit_interval_capped_at_300():
    hub = _hub(make_handler())
    hub.register_rate_limit(400)
    assert hub.next_poll_delay() == 300  # ust sinir


def test_rate_limit_error_from_fetch_propagates():
    handler = make_handler(rate_limit_path="/stats/top", retry_after="30")

    async def run() -> None:
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = AsyncFlorenceClient(
            transport=httpx.MockTransport(handler),
            token_store=store,
            max_retries=0,
        )
        hub = DataHub(client=client, refresh_seconds=45)
        with pytest.raises(RateLimitError):
            await hub.fetch_dashboard()
        # App seviyesinde kaydedilir:
        hub.register_rate_limit(30)
        assert hub.next_poll_delay() == 90

    asyncio.run(run())


# ----------------------------------------------------------------------
# K4 — piyasa kapaliyken planlama
# ----------------------------------------------------------------------
def test_market_closed_plans_next_open_at():
    # 2026-08-14 20:00 UTC; next_open_at 2026-08-15T10:00+03:00 = 07:00 UTC.
    fixed = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    handler = make_handler(status_json={"open": False, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False})

    async def run() -> None:
        hub = _hub(handler, clock=lambda: fixed)
        status = await hub.get_market_status()
        assert status["open"] is False
        # (07:00 - 20:00) = 11 saat = 39600s + ~1dk pay (K4)
        assert hub.next_poll_delay() == pytest.approx(39600 + 60)

    asyncio.run(run())


def test_market_closed_without_next_open_at_falls_back_5min():
    fixed = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    handler = make_handler(status_json={"open": False, "next_open_at": None, "holiday": False})

    async def run() -> None:
        hub = _hub(handler, market_closed_refresh=300, clock=lambda: fixed)
        await hub.get_market_status()
        assert hub.next_poll_delay() == 300  # 5dk fallback (K4)

    asyncio.run(run())


def test_first_request_always_made_before_status_known():
    # Henuz market_status cekilmemisken planlama normal intervaldir (K4).
    hub = _hub(make_handler(), refresh_seconds=45, market_closed_refresh=300)
    assert hub.next_poll_delay() == 45
    assert hub._market_status_fetched is False


def test_open_market_keeps_normal_interval():
    async def run() -> None:
        hub = _hub(make_handler(status_open=True))
        await hub.get_market_status()
        assert hub.next_poll_delay() == 45

    asyncio.run(run())


# ----------------------------------------------------------------------
# Auth bolumleri (canli backend dogrulamasi)
# ----------------------------------------------------------------------
def test_fetch_dashboard_skips_auth_sections_without_token(make_client):
    async def run() -> None:
        client = make_client(make_handler(), authenticated=False)
        hub = DataHub(client=client)
        snap = await hub.fetch_dashboard()
        # Public kisim calisir:
        assert snap.market_status is not None
        assert snap.market_status["open"] is True
        # Auth-gerektiren bolumler atlanir:
        assert snap.stats_top is None
        assert snap.auth_sections == AUTH_REQUIRED_SECTIONS
        assert not snap.errors  # hata degil, bilincli atlama

    asyncio.run(run())


def test_fetch_dashboard_fetches_all_with_token(make_client):
    async def run() -> None:
        client = make_client(make_handler(), authenticated=True)
        hub = DataHub(client=client)
        snap = await hub.fetch_dashboard()
        assert snap.market_status is not None
        assert snap.market_status["open"] is True
        assert snap.stats_top is not None
        assert [r["ticker"] for r in snap.stats_top] == ["THYAO", "ASELS", "GARAN"]
        assert snap.gainers is not None and snap.gainers[0]["ticker"] == "THYAO"
        assert snap.losers is not None and snap.losers[0]["ticker"] == "GARAN"
        assert snap.gold is not None and snap.gold[0]["Buying"] == "40,25"
        assert snap.currency is not None and snap.currency["USD"]["buying"] == "42,10"
        assert not snap.errors
        assert snap.auth_sections == ()

    asyncio.run(run())


def test_fetch_dashboard_tolerates_section_errors(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/market/status"):
            return httpx.Response(200, json=MOCK_STATUS_OPEN)
        if path.endswith("/stats/top"):
            return httpx.Response(500, json={"detail": "error_internal"})
        if path.endswith("/companies/summary"):
            return httpx.Response(200, json=[{"ticker": "THYAO", "price": 313.4, "change_pct": 0.93}])
        if path.endswith("/economy/gold-prices"):
            return httpx.Response(200, json=[])
        if path.endswith("/economy/currency"):
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        client = make_client(handler, authenticated=True)
        hub = DataHub(client=client)
        snap = await hub.fetch_dashboard()
        assert snap.stats_top is None
        assert "stats_top" in snap.errors
        assert snap.errors["stats_top"] == "API hatası 500"
        # Diger bolumler etkilenmez:
        assert snap.gainers is not None
        assert snap.gold == []
        assert not snap.errors.get("gainers")

    asyncio.run(run())


# ----------------------------------------------------------------------
# Format yardimcilari (Ek A sozlesmeleri)
# ----------------------------------------------------------------------
def test_tr_number_format():
    assert tr_number(313.4) == "313,40"
    assert tr_number(1234.5) == "1.234,50"
    assert tr_number(0) == "0,00"
    assert tr_number("gecersiz") == "—"


def test_tr_delta_format():
    assert tr_delta(0.93) == "+0,93%"
    assert tr_delta(-1.2) == "-1,20%"
    assert tr_delta(0) == "0,00%"


def test_delta_style_tr_bist():
    assert delta_style(1) == "$success"
    assert delta_style(-1) == "$error"
    assert delta_style(0) == "$foreground"
    assert delta_style(None) == "$foreground"


def test_gold_summary_selects_preferred_items():
    gold = [
        {"Type": "Gram Altın", "Buying": "40,25"},
        {"Type": "Çeyrek Altın", "Buying": "3.450,00"},
        {"Type": "Gümüş", "Buying": "30,5"},
    ]
    items = gold_summary(gold)
    assert [label for label, _ in items] == ["Gram Altın", "Çeyrek Altın"]
    assert items[0][1]["Buying"] == "40,25"


def test_gold_summary_empty():
    assert gold_summary([]) == []
    assert gold_summary([{"Type": "Gümüş", "Buying": "1"}]) == []


def test_error_message_mapping():
    from florence.errors import NetworkError

    assert error_message(NetworkError("x")) == "Bağlantı hatası"
