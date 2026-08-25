"""PORTFÖY ekrani + fetch_portfolio testleri (Faz E — P7, TAMAMEN OFFLINE).

Kapsam (plan T-E1..T-E4):
- ``DataHub.fetch_portfolio``: list + snapshot + history + performers,
  auth'suz atlama, kismi hata toleransi, cache, tek portfoyde otomatik secim.
- ``PortfolioScreen``: listeleme + secim, ozet satiri (TR format), ccharts
  grafik render (sentez + tam OHLC yollari), auth uyarisi, bos liste,
  ``4`` tusu gecisi, ``esc`` geri donus (switch — push degil), period tuslari.

Mock sema (P7): canli backend bu makinede kalkik olmadigindan alan adlari
kod okumasi + helpers-design.md H5 sozlesmesinden alindi (uydurma yok);
canli dogrulama Faz F'ye ertelendi (plan risk 7).
"""

from __future__ import annotations

import asyncio

import httpx
from textual.widgets import ContentSwitcher, DataTable, Static

from florence import AsyncFlorenceClient, MemoryTokenStore
from florence.tui.data import DataHub
from florence.tui.screens.portfolio import (
    PortfolioScreen,
    portfolio_chart_rows,
)

from .conftest import (
    MOCK_PORTFOLIO_HISTORY,
    MOCK_PORTFOLIO_HISTORY_OHLC,
    make_handler,
    wait_for,
)

_BLOCK_CHARS = "▁▂▃▄▅▆▇█"


def _row_count(app, table_id: str) -> int:
    try:
        return app.screen.query_one(f"#{table_id}", DataTable).row_count
    except Exception:
        return 0


def _state(app) -> str | None:
    try:
        return app.screen.query_one("#portfolio-switcher", ContentSwitcher).current
    except Exception:
        return None


def _text(app, widget_id: str) -> str:
    try:
        return str(app.screen.query_one(f"#{widget_id}", Static).render())
    except Exception:
        return ""


def _hub(handler, *, authenticated: bool = True) -> DataHub:
    store = MemoryTokenStore()
    if authenticated:
        store.set_tokens("at-1", "rt-1")
    client = AsyncFlorenceClient(
        transport=httpx.MockTransport(handler),
        token_store=store,
        max_retries=0,
    )
    return DataHub(client=client)


# ----------------------------------------------------------------------
# T-E1 — DataHub.fetch_portfolio birim testleri
# ----------------------------------------------------------------------
def test_fetch_portfolio_fetches_all_with_token():
    """Token ile: liste + snapshot + history + performers tek pakette doner."""

    async def run() -> None:
        hub = _hub(make_handler())
        snap = await hub.fetch_portfolio("7")
        assert snap.market_status is not None and snap.market_status["open"] is True
        # Liste: H5 sozlesmesi alan adlari (id/name/initial_balance).
        assert snap.summaries is not None and len(snap.summaries) == 2
        first = snap.summaries[0]
        assert first.portfolio_id == "7"
        assert first.name == "Benim Portföyüm"
        assert first.initial_balance == 100000.0
        assert snap.portfolio_id == "7"
        # Snapshot ozeti
        assert snap.summary is not None
        assert snap.summary["total_value"] == 152340.5
        assert snap.summary["pnl_pct"] == 8.8
        # History deger serisi + performans
        assert snap.history == MOCK_PORTFOLIO_HISTORY
        assert snap.performers is not None
        assert snap.performers[0].ticker == "THYAO"
        assert snap.performers[0].return_pct == 8.8
        assert snap.auth_sections == ()
        assert not snap.errors

    asyncio.run(run())


def test_fetch_portfolio_skips_without_token():
    """Auth yoksa portfoy uclarina HIC istek atilmaz (auth_sections)."""
    portfolio_requests = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/portfolios" in request.url.path:
            portfolio_requests["n"] += 1
        return make_handler()(request)

    async def run() -> None:
        hub = _hub(handler, authenticated=False)
        snap = await hub.fetch_portfolio("7")
        # Public kisim (market/status) calisir; portfoy verisi bilincli atlanir.
        assert snap.market_status is not None
        assert snap.summaries is None
        assert snap.summary is None
        assert snap.history is None
        assert snap.performers is None
        assert snap.auth_sections == ("portfolio",)
        assert portfolio_requests["n"] == 0

    asyncio.run(run())


def test_fetch_portfolio_partial_snapshot_failure_keeps_list():
    """Kismi hata toleransi: snapshot duserse liste + history + performers kalir."""

    async def run() -> None:
        hub = _hub(make_handler(portfolio_fail_snapshot=True))
        snap = await hub.fetch_portfolio("7")
        assert snap.summaries is not None and len(snap.summaries) == 2
        assert snap.summary is None  # snapshot hata -> ozet yok
        assert "portfolio_snapshot" in snap.errors
        assert snap.history == MOCK_PORTFOLIO_HISTORY  # diger bolumler etkilenmez
        assert snap.performers is not None
        assert snap.portfolio_id == "7"

    asyncio.run(run())


def test_fetch_portfolio_second_call_served_from_cache():
    """Cache: ikinci cagri hicbir HTTP istegi atmaz (list 60s / snap 60s / hist 10dk)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return make_handler()(request)

    async def run() -> None:
        hub = _hub(handler)
        await hub.fetch_portfolio("7")
        calls["n"] = 0
        snap = await hub.fetch_portfolio("7")
        assert snap.summaries is not None and len(snap.summaries) == 2
        assert snap.summary is not None
        assert snap.history == MOCK_PORTFOLIO_HISTORY
        assert calls["n"] == 0

    asyncio.run(run())


def test_fetch_portfolio_auto_selects_single_portfolio():
    """Tek portfoy varsa id verilmese bile otomatik secilir."""

    async def run() -> None:
        hub = _hub(make_handler(portfolios=[{"id": 3, "name": "Tek"}]))
        snap = await hub.fetch_portfolio(None)
        assert len(snap.summaries) == 1
        assert snap.portfolio_id == "3"  # otomatik secim -> snapshot cekildi
        assert snap.summary is not None

    asyncio.run(run())


# ----------------------------------------------------------------------
# T-E3 — grafik veri beslemesi (sentez + tam OHLC)
# ----------------------------------------------------------------------
def test_portfolio_chart_rows_synthesizes_value_series():
    """OHLC yoksa ``{ts, value}`` -> ``{ts, open, close}`` sentezi (P2)."""
    rows = portfolio_chart_rows(MOCK_PORTFOLIO_HISTORY)
    assert len(rows) == 3
    # open = onceki close (ilk: kendi close'u) — trend_cell ile ayni desen.
    assert rows[0]["open"] == 140000.0
    assert rows[0]["close"] == 140000.0
    assert rows[1]["open"] == 140000.0
    assert rows[1]["close"] == 148000.0
    assert rows[2]["open"] == 148000.0
    assert rows[2]["close"] == 152340.5
    # ts korunur -> show_times dogru basar.
    assert rows[0]["ts"] == "2026-07-01T00:00:00+00:00"


def test_portfolio_chart_rows_keeps_full_ohlc():
    """Tam OHLC varsa birebir korunur (high/low sentezlenmez — P2)."""
    rows = portfolio_chart_rows(MOCK_PORTFOLIO_HISTORY_OHLC)
    assert len(rows) == 3
    assert rows[1]["open"] == 140000.0
    assert rows[1]["high"] == 149000.0
    assert rows[1]["low"] == 139500.0
    assert rows[1]["close"] == 148000.0


def test_portfolio_chart_rows_skips_invalid_values():
    """Gecersiz value satirlari atilir (ccharts null kabul etmez)."""
    rows = portfolio_chart_rows(
        [
            {"ts": "2026-07-01", "value": 100.0},
            {"ts": "2026-07-02", "value": "gecersiz"},
            {"ts": "2026-07-03"},
            {"ts": "2026-07-04", "value": 120.0},
        ]
    )
    assert [r["close"] for r in rows] == [100.0, 120.0]


# ----------------------------------------------------------------------
# T-E2 + T-E4 — ekran testleri (run_test + pilot)
# ----------------------------------------------------------------------
def test_portfolio_key_and_escape_navigation(make_app):
    """``5`` portfoye gecirir; ``esc`` geldigi ekrana doner (switch, push degil)."""

    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            # Dashboard -> 5 -> Portfolio
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: _row_count(app, "portfolio-table") == 2)
            # esc -> dashboard'a doner (switch; stack'e push edilmedi)
            await pilot.press("escape")
            await wait_for(app, lambda: type(app.screen).__name__ == "DashboardScreen")
            # Watchlist -> 5 -> Portfolio; esc -> watchlist'e doner
            await pilot.press("3")
            await wait_for(app, lambda: type(app.screen).__name__ == "WatchlistScreen")
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await pilot.press("escape")
            await wait_for(app, lambda: type(app.screen).__name__ == "WatchlistScreen")
            # Serbest gezinme: watchlist'ten 1 -> dashboard, 5 -> portfolio
            await pilot.press("1")
            await wait_for(app, lambda: type(app.screen).__name__ == "DashboardScreen")
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))

    asyncio.run(run())


def test_portfolio_select_row_shows_summary_chart_performers(make_app):
    """Satir sec (enter) -> ozet satiri + ccharts grafik + performers tablosu."""

    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: _row_count(app, "portfolio-table") == 2)
            table = app.screen.query_one("#portfolio-table", DataTable)
            table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            # Secim sonrasi snapshot+grafik+performers cekilir.
            await wait_for(app, lambda: "Toplam" in _text(app, "portfolio-summary"))
            assert app.screen.portfolio_id == "7"
            # Ozet: TR format (toplam deger + donem getirisi)
            summary = _text(app, "portfolio-summary")
            assert "152.340,50" in summary
            assert "+8,80%" in summary
            # Grafik: value serisi sentezlendi -> ccharts line render
            chart_out = _text(app, "portfolio-chart")
            assert any(ch in chart_out for ch in _BLOCK_CHARS)
            assert "2026-07-01" in chart_out  # show_times
            # Performers tablosu: Ticker / Getiri
            perfs = app.screen.query_one("#performers-table", DataTable)
            assert perfs.row_count == 2
            assert str(perfs.get_row_at(0)[0]) == "THYAO"
            assert str(perfs.get_row_at(0)[1]) == "+8,80%"
            # Ust bar: piyasa durumu + son guncelleme
            bar = _text(app, "portfolio-status")
            assert "AÇIK" in bar
            assert "Son güncelleme" in bar

    asyncio.run(run())


def test_portfolio_screen_auto_selects_single(make_app):
    """Tek portfoy: enter gerekmeden otomatik secilir ve ozet cizilir."""

    async def run() -> None:
        app = make_app(make_handler(portfolios=[{"id": 3, "name": "Tek"}]))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: "Toplam" in _text(app, "portfolio-summary"))
            assert app.screen.portfolio_id == "3"
            assert _row_count(app, "portfolio-table") == 1

    asyncio.run(run())


def test_portfolio_screen_auth_required_without_token(make_app):
    """Auth yoksa uyari gosterilir; public market/status yine calisir."""

    async def run() -> None:
        app = make_app(make_handler(), authenticated=False)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: _state(app) == "portfolio-auth")
            assert "fl auth login" in _text(app, "portfolio-auth")
            assert "AÇIK" in _text(app, "portfolio-status")

    asyncio.run(run())


def test_portfolio_screen_empty_list_suggests_cli_create(make_app):
    """Portfoy yoksa CLI ile olusturma yonlendirmesi gosterilir."""

    async def run() -> None:
        app = make_app(make_handler(portfolios=[]))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: _state(app) == "portfolio-empty")
            text = _text(app, "portfolio-empty")
            assert "Portföyünüz yok" in text
            assert "fl portfolio create" in text

    asyncio.run(run())


def test_portfolio_period_keys_refetch_and_rerender(make_app):
    """``1/3/6/y`` period tuslari detayla ayni — history yeni periodla cekilir."""

    async def run() -> None:
        seen: dict[str, list[str | None]] = {"periods": []}
        base = make_handler()

        def handler(request: httpx.Request) -> httpx.Response:
            if "/portfolios/" in request.url.path and request.url.path.endswith("/history"):
                seen["periods"].append(request.url.params.get("period"))
            return base(request)

        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: _row_count(app, "portfolio-table") == 2)
            table = app.screen.query_one("#portfolio-table", DataTable)
            table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await wait_for(app, lambda: "Toplam" in _text(app, "portfolio-summary"))
            assert app.screen.period == "1mo"
            # 3 -> 3mo: aninda yeniden fetch + baslik guncellenir
            await pilot.press("3")
            await wait_for(app, lambda: "3mo" in seen["periods"])
            await wait_for(app, lambda: "GRAFİK (3 Ay · çizgi)" in _text(app, "portfolio-chart-title"))
            assert app.screen.period == "3mo"
            # Ayni period'a tekrar basmak yeni istek atmaz
            before = len(seen["periods"])
            await pilot.press("3")
            assert len(seen["periods"]) == before
            # 6 -> 6mo
            await pilot.press("6")
            await wait_for(app, lambda: "6mo" in seen["periods"])
            assert app.screen.period == "6mo"

    asyncio.run(run())


def test_portfolio_chart_renders_full_ohlc_and_candle_toggle(make_app):
    """Tam OHLC history birebir cizilir; ``c`` ile mum/çizgi toggle (P6)."""

    async def run() -> None:
        app = make_app(make_handler(portfolio_history=MOCK_PORTFOLIO_HISTORY_OHLC))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            await wait_for(app, lambda: _row_count(app, "portfolio-table") == 2)
            table = app.screen.query_one("#portfolio-table", DataTable)
            table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await wait_for(app, lambda: "Toplam" in _text(app, "portfolio-summary"))
            # ccharts line (show_prices/show_times etiketli)
            chart_out = _text(app, "portfolio-chart")
            assert any(ch in chart_out for ch in _BLOCK_CHARS)
            assert "2026-07-01" in chart_out
            # c -> mum (wick karakteri)
            await pilot.press("c")
            await wait_for(app, lambda: "│" in _text(app, "portfolio-chart"))
            assert "GRAFİK (1 Ay · mum)" in _text(app, "portfolio-chart-title")
            # c -> geri çizgi
            await pilot.press("c")
            await wait_for(app, lambda: _text(app, "portfolio-chart-title") == "GRAFİK (1 Ay · çizgi)")

    asyncio.run(run())


def test_help_modal_lists_portfolio_key(make_app):
    """Yardim panelinde ``5`` (Portfoy) satiri guncellenir (T-E4)."""

    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("h")
            from textual.containers import Vertical

            from florence.tui.app import HelpModal

            assert isinstance(app.screen, HelpModal)
            box = app.screen.query_one("#help-box", Vertical)
            text = str(box.query_one(Static).render())
            assert "5" in text
            assert "Portföy" in text

    asyncio.run(run())