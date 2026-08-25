"""IZLEME LISTESI ekrani + fetch_watchlist testleri (TAMAMEN OFFLINE).

Tasarim §8: mock transport'lu client + ``FlorenceTUI`` -> ``run_test``.
Kapsam: mock veriyle render (fiyat/Δ%/trend — ccharts mini line, K2), bos
watchlist, auth yok uyarisi, kismi fiyat hatasi toleransi, satir sec -> detay
acilisi, ``trend_cell`` saf fonksiyonu ve ``DataHub.fetch_watchlist`` birim
testleri.

Not: App.query() push edilmis ekrani gormez (Textual 8.x) — widget
sorgulari ``app.screen`` uzerinden yapilir.
"""

from __future__ import annotations

import asyncio

import httpx
from textual.widgets import ContentSwitcher, DataTable, Static

from florence import AsyncFlorenceClient, MemoryTokenStore
from florence.tui.data import DataHub
from florence.tui.screens.detail import DetailScreen
from florence.tui.screens.watchlist import WatchlistScreen, trend_cell

from .conftest import make_handler, wait_for

#: Trend hucresi renk testi icin tema (P4 kofrusu — gercek tema degil).
TEST_THEME = {"success": "#1a8a5c", "error": "#dc322f"}

#: ccharts line ciktisindaki 8 seviye blok karakterler (K2/P5).
_BLOCK_CHARS = "▁▂▃▄▅▆▇█"


def _has_block_chars(cell) -> bool:
    return any(ch in str(cell) for ch in _BLOCK_CHARS)


def _has_color_span(cell) -> bool:
    """Rich Text span'larinda on plan rengi var mi (Rich 15: ``Style.color``)."""
    return any(
        getattr(span.style, "color", None) is not None
        for span in getattr(cell, "spans", ())
    )


def _row_count(app, table_id: str) -> int:
    try:
        return app.screen.query_one(f"#{table_id}", DataTable).row_count
    except Exception:
        return 0


def _state(app, switcher_id: str = "watchlist-switcher") -> str | None:
    try:
        return app.screen.query_one(f"#{switcher_id}", ContentSwitcher).current
    except Exception:
        return None


def _text(app, widget_id: str) -> str:
    try:
        return str(app.screen.query_one(f"#{widget_id}", Static).render())
    except Exception:
        return ""


# ----------------------------------------------------------------------
# Ekran testleri (run_test + pilot)
# ----------------------------------------------------------------------
def test_watchlist_renders_favorites_with_prices_and_sparkline(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            await wait_for(app, lambda: _row_count(app, "watchlist-table") == 2)
            table = app.screen.query_one("#watchlist-table", DataTable)
            row0 = list(table.get_row_at(0))
            assert str(row0[0]) == "THYAO"
            assert str(row0[1]) == "313,40"  # TR format
            assert str(row0[2]) == "+0,93%"
            # Trend: ccharts height=1 mini line (K2 — Sparkline degil).
            # Render davranisina dayali: blok karakterler + renkli span.
            assert _has_block_chars(row0[3])
            assert "\n" not in str(row0[3])  # tek satir (DataTable hucresi)
            assert _has_color_span(row0[3])
            row1 = list(table.get_row_at(1))
            assert str(row1[0]) == "ASELS"
            assert str(row1[1]) == "1.234,50"
            assert str(row1[2]) == "-1,20%"
            # Ust bar: piyasa durumu + son guncelleme
            bar = _text(app, "watchlist-status")
            assert "AÇIK" in bar
            assert "Son güncelleme" in bar

    asyncio.run(run())


def test_watchlist_empty_state_suggests_cli_add(make_app):
    async def run() -> None:
        app = make_app(make_handler(favorites=[]))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            await wait_for(app, lambda: _state(app) == "watchlist-empty")
            text = _text(app, "watchlist-empty")
            assert "Favoriniz yok" in text
            assert "fl portfolio favorite add THYAO" in text

    asyncio.run(run())


def test_watchlist_auth_required_without_token(make_app):
    async def run() -> None:
        app = make_app(make_handler(), authenticated=False)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            await wait_for(app, lambda: _state(app) == "watchlist-auth")
            assert "fl auth login" in _text(app, "watchlist-auth")
            # Public kisim (market/status) yine calisir
            assert "AÇIK" in _text(app, "watchlist-status")

    asyncio.run(run())


def test_watchlist_partial_price_failure_keeps_list(make_app):
    async def run() -> None:
        app = make_app(make_handler(price_fail_tickers={"ASELS"}))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            await wait_for(app, lambda: _row_count(app, "watchlist-table") == 2)
            table = app.screen.query_one("#watchlist-table", DataTable)
            # Saglam satir tam dolu
            row0 = list(table.get_row_at(0))
            assert str(row0[0]) == "THYAO"
            assert str(row0[1]) == "313,40"
            # Hatali satir '—' gosterir ama listeden dusmez
            row1 = list(table.get_row_at(1))
            assert str(row1[0]) == "ASELS"
            assert str(row1[1]) == "—"
            assert str(row1[2]) == "—"
            assert _row_count(app, "watchlist-table") == 2

    asyncio.run(run())


def test_watchlist_enter_opens_detail(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            await wait_for(app, lambda: _row_count(app, "watchlist-table") == 2)
            table = app.screen.query_one("#watchlist-table", DataTable)
            table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            assert app.screen.ticker == "THYAO"

    asyncio.run(run())


# ----------------------------------------------------------------------
# trend_cell birim testleri (saf fonksiyon — Faz B, K2/P5)
# ----------------------------------------------------------------------
def test_trend_cell_renders_ccharts_mini_line():
    """Close serisi -> ccharts height=1 line hucresi: blok + renkli tek satir."""
    cell = trend_cell([310.0, 313.4, 312.0], TEST_THEME)
    assert _has_block_chars(cell)
    assert "\n" not in str(cell)  # DataTable hucresi tek satir
    assert _has_color_span(cell)  # single_color: ANSI -> Text span


def test_trend_cell_empty_values_returns_em_dash():
    assert str(trend_cell([], TEST_THEME)) == "—"
    assert str(trend_cell([None, None], TEST_THEME)) == "—"


def test_trend_cell_without_theme_uses_ccharts_defaults():
    # Tema yoksa period_colors (None, None) -> ccharts default renkler (P4
    # fallback). Hucresi yine cizilir (blok karakterler var).
    cell = trend_cell([10.0, 20.0, 30.0], None)
    assert _has_block_chars(cell)
    assert _has_color_span(cell)


def test_trend_cell_respects_width():
    cell = trend_cell([10.0, 20.0, 30.0], TEST_THEME, width=6)
    assert _has_block_chars(cell)


# ----------------------------------------------------------------------
# DataHub.fetch_watchlist birim testleri
# ----------------------------------------------------------------------
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


def test_fetch_watchlist_fetches_all_with_token():
    async def run() -> None:
        hub = _hub(make_handler())
        snap = await hub.fetch_watchlist()
        assert snap.market_status is not None and snap.market_status["open"] is True
        assert snap.favorites == ["THYAO", "ASELS"]
        assert len(snap.rows) == 2
        assert snap.rows[0].ticker == "THYAO"
        assert snap.rows[0].price == 313.4
        assert snap.rows[0].change_pct == 0.93
        assert snap.rows[0].close_values == [310.0, 313.4, 312.0]
        assert snap.rows[1].ticker == "ASELS"
        assert snap.auth_sections == ()
        assert not snap.errors

    asyncio.run(run())


def test_fetch_watchlist_skips_without_token():
    async def run() -> None:
        hub = _hub(make_handler(), authenticated=False)
        snap = await hub.fetch_watchlist()
        # Public kisim calisir; favoriler bilincli atlanir (istek yok).
        assert snap.market_status is not None
        assert snap.favorites is None
        assert snap.rows == []
        assert snap.auth_sections == ("favorites",)
        assert not snap.errors

    asyncio.run(run())


def test_fetch_watchlist_tolerates_partial_price_failure():
    async def run() -> None:
        hub = _hub(make_handler(price_fail_tickers={"ASELS"}))
        snap = await hub.fetch_watchlist()
        assert len(snap.rows) == 2  # liste dusmez
        assert snap.rows[0].price == 313.4
        assert snap.rows[1].price is None  # kismi hata -> '—'
        assert "price:ASELS" in snap.errors
        assert snap.favorites == ["THYAO", "ASELS"]

    asyncio.run(run())


def test_fetch_watchlist_second_call_served_from_cache():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path.endswith("/favorites"):
            return httpx.Response(200, json=["THYAO"])
        return make_handler()(request)

    async def run() -> None:
        hub = _hub(handler)
        await hub.fetch_watchlist()
        calls["n"] = 0  # sayaci sifirla
        snap = await hub.fetch_watchlist()
        assert snap.rows[0].ticker == "THYAO"
        # Tum veriler cache'ten (favorites 60s, fiyat 60s, seri 10dk).
        assert calls["n"] == 0

    asyncio.run(run())
