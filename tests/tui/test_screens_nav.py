"""TUI çok sekmeli navigasyon ve yeni ekran testleri (TAMAMEN OFFLINE)."""

from __future__ import annotations

import asyncio

import httpx
from textual.widgets import ContentSwitcher, Static

from florence.tui.charts import candle_colors
from florence.tui.screens.dashboard import DashboardScreen
from florence.tui.screens.detail import DetailScreen
from florence.tui.screens.digest import DigestScreen
from florence.tui.screens.economy import EconomyScreen
from florence.tui.screens.portfolio import PortfolioScreen
from florence.tui.screens.stocks import StocksScreen
from florence.tui.screens.watchlist import WatchlistScreen
from florence.tui.widgets.nav import AppHeader, NavBar

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
    """1-6 tuşları ile sekmeler arası sorunsuz geçiş: 1 Pano, 2 Hisseler, 3 İzleme, 4 Bülten, 5 Portföy, 6 Ekonomi."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/digest"):
            return httpx.Response(200, json=MOCK_DIGEST)
        return make_handler()(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            # 1: Pano
            assert isinstance(app.screen, DashboardScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-dashboard"

            # 2: Hisseler
            await pilot.press("2")
            await wait_for(app, lambda: isinstance(app.screen, StocksScreen))
            assert isinstance(app.screen, StocksScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-stocks"

            # 3: İzleme
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            assert isinstance(app.screen, WatchlistScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-watchlist"

            # 4: Bülten
            await pilot.press("4")
            await wait_for(app, lambda: isinstance(app.screen, DigestScreen))
            assert isinstance(app.screen, DigestScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-digest"

            # 5: Portföy
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            assert isinstance(app.screen, PortfolioScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-portfolio"

            # 6: Ekonomi
            await pilot.press("6")
            await wait_for(app, lambda: isinstance(app.screen, EconomyScreen))
            assert isinstance(app.screen, EconomyScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-economy"

            # Geri 1: Pano
            await pilot.press("1")
            await wait_for(app, lambda: isinstance(app.screen, DashboardScreen))
            assert isinstance(app.screen, DashboardScreen)
            nav = app.screen.query_one(NavBar)
            assert nav.active == "tab-dashboard"

    asyncio.run(run())


def test_tui_mouse_tab_navigation(make_app):
    """Mouse ile sekme tıklamaları (Tabs.TabActivated) ile ekran geçişleri."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/digest"):
            return httpx.Response(200, json=MOCK_DIGEST)
        return make_handler()(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, DashboardScreen)

            # Click tab-stocks
            await pilot.click("#tab-stocks")
            await wait_for(app, lambda: isinstance(app.screen, StocksScreen))
            assert isinstance(app.screen, StocksScreen)

            # Click tab-watchlist
            await pilot.click("#tab-watchlist")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            assert isinstance(app.screen, WatchlistScreen)

            # Click tab-digest
            await pilot.click("#tab-digest")
            await wait_for(app, lambda: isinstance(app.screen, DigestScreen))
            assert isinstance(app.screen, DigestScreen)

            # Click tab-portfolio
            await pilot.click("#tab-portfolio")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            assert isinstance(app.screen, PortfolioScreen)

            # Click tab-economy
            await pilot.click("#tab-economy")
            await wait_for(app, lambda: isinstance(app.screen, EconomyScreen))
            assert isinstance(app.screen, EconomyScreen)

            # Click tab-dashboard
            await pilot.click("#tab-dashboard")
            await wait_for(app, lambda: isinstance(app.screen, DashboardScreen))
            assert isinstance(app.screen, DashboardScreen)

    asyncio.run(run())


def test_tui_app_header_on_all_screens(make_app):
    """Tüm ekranlarda (Pano, Hisseler, İzleme, Bülten, Portföy, Ekonomi, Detay) AppHeader ve ASCII logo gösterimi."""
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            # 1. Pano
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

            # 2. Hisseler
            await pilot.press("2")
            await wait_for(app, lambda: isinstance(app.screen, StocksScreen))
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

            # 3. İzleme
            await pilot.press("3")
            await wait_for(app, lambda: isinstance(app.screen, WatchlistScreen))
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

            # 4. Bülten
            await pilot.press("4")
            await wait_for(app, lambda: isinstance(app.screen, DigestScreen))
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

            # 5. Portföy
            await pilot.press("5")
            await wait_for(app, lambda: isinstance(app.screen, PortfolioScreen))
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

            # 6. Ekonomi
            await pilot.press("6")
            await wait_for(app, lambda: isinstance(app.screen, EconomyScreen))
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

            # 7. Detay
            app.open_detail("THYAO")
            await wait_for(
                app,
                lambda: isinstance(app.screen, DetailScreen) and len(app.screen.query(AppHeader)) > 0,
            )
            assert app.screen.query_one(AppHeader) is not None
            assert app.screen.query_one("#banner-art", Static) is not None

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
            await pilot.press("4")
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
            await pilot.press("2")
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
