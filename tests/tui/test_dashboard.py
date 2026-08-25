"""Pano ekranı testleri: App.run_test (headless) ile render + durumlar.

Tasarım §8.1: mock transport'lu client + ``FlorenceTUI`` -> ``run_test``.
Kapsam: web benzeri kart tasarımı mock veriyle render, auth yok uyarısı,
429 banner'ı, boş durumlar, gainers/losers sekmesi, kapalı piyasa,
yardım paneli, Detay ekranına geçiş, bülten kısayolu.
"""

from __future__ import annotations

import asyncio

import httpx
from textual.widgets import DataTable, Static

from florence.tui.app import FlorenceTUI, HelpModal
from florence.tui.screens.dashboard import (
    DashboardScreen,
)
from florence.tui.screens.detail import DetailScreen
from florence.tui.screens.digest import DigestScreen

from .conftest import make_handler, wait_for


def _row_count(app: FlorenceTUI, table_id: str) -> int:
    try:
        return app.screen.query_one(f"#{table_id}", DataTable).row_count
    except Exception:
        return 0


def _state(app: FlorenceTUI, widget_id: str) -> str | None:
    try:
        widget = app.screen.query_one(f"#{widget_id}")
        if hasattr(widget, "current_state"):
            return str(widget.current_state())
        return None
    except Exception:
        return None


def _text(app: FlorenceTUI, widget_id: str) -> str:
    try:
        return str(app.screen.query_one(f"#{widget_id}", Static).render())
    except Exception:
        return ""


def test_dashboard_renders_mock_data(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _row_count(app, "popular-table") == 3)
            popular = app.screen.query_one("#popular-table", DataTable)
            movers = app.screen.query_one("#movers", DataTable)

            # Popüler hisseler kart ızgarası
            assert str(popular.get_row_at(0)[0]) == "THYAO"
            assert str(popular.get_row_at(0)[2]) == "313,40"
            assert str(popular.get_row_at(0)[3]) == "+0,93%"
            assert "1,25 Mr" in str(popular.get_row_at(0)[4])

            # Günün hareketleri (varsayılan sekme: Gainers)
            assert movers.row_count == 2
            assert str(movers.get_row_at(0)[0]) == "THYAO"
            assert str(movers.get_row_at(0)[1]) == "313,40"
            assert str(movers.get_row_at(0)[2]) == "+0,93%"

            # Üst bar: piyasa açık + son güncelleme
            bar = _text(app, "status-bar")
            assert "AÇIK" in bar
            assert "Son güncelleme" in bar

            # Favoriler kart şeridi
            fav_text = _text(app, "favorites-content")
            assert "THYAO" in fav_text
            assert "313,40" in fav_text

            # Günün bülteni kartı
            digest_text = _text(app, "digest-content")
            assert "Günün Piyasa Özeti" in digest_text
            assert "Sabah" in digest_text

            # Döviz & Altın piyasası kartı
            econ_text = _text(app, "economy-content")
            assert "Gram Altın 40,25" in econ_text
            assert "USD/TRY 42,10" in econ_text
            assert "EUR/TRY 45,30" in econ_text

    asyncio.run(run())


def test_dashboard_auth_required_warning_without_token(make_app):
    async def run() -> None:
        app = make_app(make_handler(), authenticated=False)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _state(app, "popular-panel") == "auth")
            # Auth-gerektiren kartlar ve paneller uyarı gösterir
            assert _state(app, "movers-panel") == "auth"
            assert _state(app, "favorites-card") == "auth"
            assert _state(app, "digest-card") == "auth"
            assert _state(app, "economy-card") == "auth"

            assert "Giriş yapın (fl auth login)" in _text(app, "popular-table-auth")
            assert "fl auth login" in _text(app, "economy-auth")
            # Public kısım (market/status) yine çalışır
            assert "AÇIK" in _text(app, "status-bar")

    asyncio.run(run())


def test_dashboard_rate_limit_banner_and_interval(make_app):
    async def run() -> None:
        handler = make_handler(rate_limit_path="/companies/summary", retry_after="30")
        app = make_app(handler, refresh_seconds=45)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: "Rate limit" in _text(app, "banner"))
            assert "Rate limit — 30s sonra tekrar deneniyor" in _text(app, "banner")
            # Interval uzatıldı (tasarım §4.4): max(45*2, 30+10) = 90
            assert app.data.next_poll_delay() == 90
            assert app.data._rate_limit_ticks == 3

    asyncio.run(run())


def test_dashboard_empty_panels_show_veri_yok(make_app):
    async def run() -> None:
        handler = make_handler(
            popular=[],
            gainers=[],
            losers=[],
            favorites_summary=[],
            gold=[],
            currency={},
        )
        app = make_app(handler)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _state(app, "popular-panel") == "empty")
            assert _state(app, "movers-panel") == "empty"
            assert _state(app, "favorites-card") == "empty"
            assert _state(app, "economy-card") == "empty"
            assert "Veri yok" in _text(app, "popular-table-empty")

    asyncio.run(run())


def test_dashboard_toggle_gainers_losers(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await wait_for(app, lambda: _row_count(app, "movers") == 2)
            # l -> Düşenler
            await pilot.press("l")
            movers = app.screen.query_one("#movers", DataTable)
            await wait_for(app, lambda: str(movers.get_row_at(0)[0]) == "GARAN")
            assert str(movers.get_row_at(0)[2]) == "-2,10%"
            # g -> Yükselenler
            await pilot.press("g")
            await wait_for(app, lambda: str(movers.get_row_at(0)[0]) == "THYAO")
            # tab -> toggle (GARAN'a doner)
            await pilot.press("tab")
            await wait_for(app, lambda: str(movers.get_row_at(0)[0]) == "GARAN")

    asyncio.run(run())


def test_dashboard_enter_opens_detail_screen(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await wait_for(app, lambda: _row_count(app, "popular-table") == 3)
            table = app.screen.query_one("#popular-table", DataTable)
            table.focus()
            table.move_cursor(row=0, column=0)
            await pilot.press("enter")
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            assert app.screen.ticker == "THYAO"

    asyncio.run(run())


def test_dashboard_digest_navigation(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await wait_for(app, lambda: _row_count(app, "popular-table") == 3)
            # '4' kısayolu bülten ekranını açar
            await pilot.press("4")
            await wait_for(app, lambda: isinstance(app.screen, DigestScreen))

    asyncio.run(run())


def test_dashboard_closed_market_status_bar(make_app):
    async def run() -> None:
        handler = make_handler(status_open=False)
        app = make_app(handler)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: "KAPALI" in _text(app, "status-bar"))
            assert "10:00'da açılacak" in _text(app, "status-bar")
            # Kapalı piyasada sonraki poll next_open_at + ~1dk pay (K4)
            assert app.data.next_poll_delay() > 45

    asyncio.run(run())


def test_dashboard_network_error_banner_keeps_old_data(make_app):
    def handler(request):
        path = request.url.path
        if path.endswith("/market/status"):
            return httpx.Response(
                200,
                json={"open": True, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False},
            )
        return httpx.Response(500, json={"detail": "error_internal"})

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: "son veri gösteriliyor" in _text(app, "banner"))
            # Bölüm hatası: panel hata durumunda
            assert _state(app, "popular-panel") == "error"
            assert "Bağlantı hatası" in _text(app, "banner") or "API hatası" in _text(app, "banner")

    asyncio.run(run())


def test_help_modal_opens_and_closes(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("h")
            assert isinstance(app.screen, HelpModal)
            await pilot.press("q")
            await wait_for(app, lambda: isinstance(app.screen, DashboardScreen))

    asyncio.run(run())


def test_active_screen_rule_only_active_fetches(make_app):
    """Aktif ekran kuralı (§4.2): tick yalnızca aktif ekranın fetch'ini çağırır."""
    import time

    async def run() -> None:
        app = make_app(make_handler())
        calls = {"dashboard": 0, "watchlist": 0}
        orig_fd, orig_fw = app.data.fetch_dashboard, app.data.fetch_watchlist

        async def fd(*args: object, **kwargs: object) -> object:
            calls["dashboard"] += 1
            return await orig_fd(*args, **kwargs)

        async def fw(*args: object, **kwargs: object) -> object:
            calls["watchlist"] += 1
            return await orig_fw(*args, **kwargs)

        app.data.fetch_dashboard, app.data.fetch_watchlist = fd, fw

        async with app.run_test(size=(120, 40)) as pilot:
            # 1) Dashboard aktif: yüklenene kadar bekle, fetch çağrılmış olmalı.
            await wait_for(app, lambda: _row_count(app, "popular-table") == 3)
            d_initial = calls["dashboard"]
            assert d_initial >= 1

            # 2) 3 ile watchlist'e geç: fetch_watchlist çağrılır,
            #    arka plandaki dashboard'un fetch'i DURUR.
            await pilot.press("3")
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if (
                    type(app.screen).__name__ == "WatchlistScreen"
                    and _row_count(app, "watchlist-table") > 0
                ):
                    break
                await asyncio.sleep(0.05)
            w1 = calls["watchlist"]
            assert w1 >= 1, "watchlist aktifken fetch_watchlist cagrilmadi"
            d_at_switch = calls["dashboard"]
            await asyncio.sleep(0.35)  # birkaç tick (refresh_seconds=0.05)
            assert calls["dashboard"] == d_at_switch, (
                "arkadaki dashboard fetch'i durmadi: "
                f"{d_at_switch} -> {calls['dashboard']}"
            )
            assert calls["watchlist"] > w1, "aktif watchlist tiklemeye devam etmiyor"

            # 3) 1 ile dön: dashboard fetch'i yeniden başlar.
            await pilot.press("1")
            await wait_for(app, lambda: isinstance(app.screen, DashboardScreen))
            await wait_for(app, lambda: _row_count(app, "popular-table") == 3)
            await asyncio.sleep(0.35)
            assert calls["dashboard"] > d_at_switch, (
                "dashboard geri aktif olunca fetch_dashboard baslamadi"
            )

    asyncio.run(run())
