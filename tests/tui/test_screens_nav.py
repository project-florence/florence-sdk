"""TUI çok sekmeli navigasyon ve yeni ekran testleri (TAMAMEN OFFLINE)."""

from __future__ import annotations

import asyncio

import httpx
from textual.widgets import ContentSwitcher, Static

from florence.tui.charts import candle_colors
from florence.tui.screens.dashboard import DashboardScreen
from florence.tui.screens.digest import DigestScreen
from florence.tui.screens.economy import EconomyScreen
from florence.tui.screens.stocks import StocksScreen
from florence.tui.screens.watchlist import WatchlistScreen

from .conftest import make_handler, wait_for

MOCK_DIGEST = {
    "title": "Günün Piyasa Özeti",
    "date": "2026-08-25",
    "slot": "morning",
    "content": "BIST 100 güne pozitif başlangıç yaptı.",
    "sections": [
        {"heading": "Öne Çıkan Gelişmeler", "body": "Havacılık ve teknoloji hisselerinde güçlü alımlar izlendi."},
    ],
}


def _text(app, widget_id: str) -> str:
    try:
        return str(app.screen.query_one(f"#{widget_id}", Static).render())
    except Exception:
        return ""


def test_tui_multi_tab_navigation(make_app):
    """1-6 tuşları ile sekmeler arası sorunsuz geçiş."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/digest"):
            return httpx.Response(200, json=MOCK_DIGEST)
        return make_handler()(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            # 1: Pano
            assert isinstance(app.screen, DashboardScreen)

            # 2: İzleme
            await pilot.press("2")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            assert isinstance(app.screen, WatchlistScreen)

            # 3: Bülten
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, DigestScreen))
            assert isinstance(app.screen, DigestScreen)

            # 5: Hisseler
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, StocksScreen))
            assert isinstance(app.screen, StocksScreen)

            # 6: Ekonomi
            await pilot.press("6")
            await wait_for(app, lambda: isinstance(app.screen, EconomyScreen))
            assert isinstance(app.screen, EconomyScreen)

            # Geri 1: Pano
            await pilot.press("1")
            await wait_for(app, lambda: isinstance(app.screen, DashboardScreen))
            assert isinstance(app.screen, DashboardScreen)

    asyncio.run(run())


def test_tui_digest_screen_renders_markdown(make_app):
    """DigestScreen markdown içeriğini ve başlıkları render eder."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/digest"):
            return httpx.Response(200, json=MOCK_DIGEST)
        return make_handler()(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, DigestScreen))
            switcher = app.screen.query_one("#digest-switcher", ContentSwitcher)
            await wait_for(app, lambda: switcher.current == "digest-container")
            assert switcher.current == "digest-container"
            snap = app.screen._last_snapshot
            assert snap is not None
            assert snap.current_digest["title"] == "Günün Piyasa Özeti"

    asyncio.run(run())


def test_tui_stocks_screen_sort_cycling(make_app):
    """StocksScreen sıralama modları ve tab döngüsü."""
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, StocksScreen))
            screen = app.screen
            assert screen.sort == "popular"

            await pilot.press("g")
            assert screen.sort == "gainers"

            await pilot.press("l")
            assert screen.sort == "losers"

            await pilot.press("tab")
            assert screen.sort == "volume"

    asyncio.run(run())


def test_candle_colors_dual_mode():
    """Mum grafiği için yeşil (rise) ve kırmızı (fall) renk ikilisi üretimi."""
    theme = {"success": "#00ff00", "error": "#ff0000"}
    rise, fall = candle_colors(theme)
    assert rise is not None
    assert fall is not None
    assert "\x1b[38;2;" in rise
    assert "\x1b[38;2;" in fall
