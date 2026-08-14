"""Pano ekrani testleri: App.run_test (headless) ile render + durumlar.

Tasarim §8.1: mock transport'lu client + ``FlorenceTUI`` -> ``run_test``.
Kapsam: mock veriyle render, auth yok uyarisi, 429 banner'i, bos durumlar,
gainers/losers sekmesi, kapali piyasa, yardim paneli.

Not: ekran mount'u asenkron oldugundan widget sorgulari kosul bekleyen
yardimcilarla yapilir (``_row_count`` / ``_text`` / ``_state``).
"""

from __future__ import annotations

import asyncio

import httpx
from textual.widgets import DataTable, Static

from florence.tui.app import FlorenceTUI, HelpModal
from florence.tui.screens.dashboard import DashboardScreen, DataPanel

from .conftest import make_handler, wait_for


def _row_count(app: FlorenceTUI, table_id: str) -> int:
    try:
        # Textual 8.x: App.query() push edilmis ekranin widget'larini gormez —
        # aktif ekrandan sorgulanir.
        return app.screen.query_one(f"#{table_id}", DataTable).row_count
    except Exception:
        return 0


def _state(app: FlorenceTUI, panel_id: str) -> str | None:
    try:
        return app.screen.query_one(f"#{panel_id}", DataPanel).current_state()
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
            await wait_for(app, lambda: _row_count(app, "stats-top") == 3)
            stats = app.screen.query_one("#stats-top", DataTable)
            movers = app.screen.query_one("#movers", DataTable)
            # One cikanlar
            assert str(stats.get_row_at(0)[0]) == "THYAO"
            assert str(stats.get_row_at(0)[1]) == "99"
            # Gunun hareketleri (varsayilan sekme: Gainers)
            assert movers.row_count == 2
            assert str(movers.get_row_at(0)[0]) == "THYAO"
            assert str(movers.get_row_at(0)[1]) == "313,40"
            assert str(movers.get_row_at(0)[2]) == "+0,93%"
            # Ust bar: piyasa acik + son guncelleme
            bar = _text(app, "status-bar")
            assert "AÇIK" in bar
            assert "Son güncelleme" in bar
            # Alt serit: altin (TR string virgul korunur) + doviz
            strip = _text(app, "economy-strip")
            assert "Gram Altın 40,25" in strip
            assert "USD/TRY 42,10" in strip
            assert "EUR/TRY 45,30" in strip

    asyncio.run(run())


def test_dashboard_auth_required_warning_without_token(make_app):
    async def run() -> None:
        app = make_app(make_handler(), authenticated=False)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _state(app, "stats-panel") == "auth")
            # Auth-gerektiren paneller uyari gosterir
            assert _state(app, "movers-panel") == "auth"
            assert "Giriş yapın (fl auth login)" in _text(app, "stats-top-auth")
            assert "fl auth login" in _text(app, "economy-strip")
            # Public kisim (market/status) yine calisir
            assert "AÇIK" in _text(app, "status-bar")

    asyncio.run(run())


def test_dashboard_rate_limit_banner_and_interval(make_app):
    async def run() -> None:
        handler = make_handler(rate_limit_path="/stats/top", retry_after="30")
        app = make_app(handler, refresh_seconds=45)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: "Rate limit" in _text(app, "banner"))
            assert "Rate limit — 30s sonra tekrar deneniyor" in _text(app, "banner")
            # Interval uzatildi (tasarim §4.4): max(45*2, 30+10) = 90
            assert app.data.next_poll_delay() == 90
            assert app.data._rate_limit_ticks == 3

    asyncio.run(run())


def test_dashboard_empty_panels_show_veri_yok(make_app):
    async def run() -> None:
        handler = make_handler(stats_top=[], gainers=[], losers=[])
        app = make_app(handler)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _state(app, "stats-panel") == "empty")
            assert _state(app, "movers-panel") == "empty"
            assert "Veri yok" in _text(app, "stats-top-empty")

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


def test_dashboard_closed_market_status_bar(make_app):
    async def run() -> None:
        handler = make_handler(
            status_json={"open": False, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False}
        )
        app = make_app(handler)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: "KAPALI" in _text(app, "status-bar"))
            assert "10:00'da açılacak" in _text(app, "status-bar")
            # Kapali piyasada sonraki poll next_open_at + ~1dk pay (K4)
            assert app.data.next_poll_delay() > 45

    asyncio.run(run())


def test_dashboard_network_error_banner_keeps_old_data(make_app):
    def handler(request):
        path = request.url.path
        if path.endswith("/market/status"):
            return httpx.Response(200, json={"open": True, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False})
        return httpx.Response(500, json={"detail": "error_internal"})

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: "son veri gösteriliyor" in _text(app, "banner"))
            # Bolum hatasi: panel hata durumunda
            assert _state(app, "stats-panel") == "error"
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
