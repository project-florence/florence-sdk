"""TICKER DETAY ekrani + fetch_detail testleri (TAMAMEN OFFLINE).

Tasarim §8: mock transport'lu client + ``FlorenceTUI`` -> ``run_test``.
Kapsam: bilgi satiri + buyuk grafik + haberler render'i, period degisimi
(``1/3/6/y`` -> aninda yeniden fetch), auth'suz haber gizleme, ``esc``
geri donus, ``fl tui`` CLI komut kaydi (smoke) ve ``DataHub.fetch_detail``
birim testleri.

Not: App.query() push edilmis ekrani gormez (Textual 8.x) — widget
sorgulari ``app.screen`` uzerinden yapilir.
"""

from __future__ import annotations

import asyncio
import contextlib
import io

import httpx
from textual.widgets import Button, DataTable, Static

from florence import AsyncFlorenceClient, MemoryTokenStore
from florence.tui.data import DataHub
from florence.tui.screens.dashboard import DashboardScreen
from florence.tui.screens.detail import DetailScreen

from .conftest import MOCK_HISTORY, make_handler, wait_for

#: Mum wick'ini (``│``) gosteren gercek ``high``/``low`` iceren history —
#: sentezlenmis high/low (P2) wick uretmez; ``c`` toggle testi buna ihtiyac duyar.
OHLC_HISTORY = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 300.0, "high": 310.0, "low": 295.0, "close": 310.0},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 310.0, "high": 314.0, "low": 308.0, "close": 313.4},
    {"ts": "2026-07-03T00:00:00+00:00", "open": 313.4, "high": 313.4, "low": 311.0, "close": 312.0},
]


def _row_count(app, table_id: str) -> int:
    try:
        return app.screen.query_one(f"#{table_id}", DataTable).row_count
    except Exception:
        return 0


def _text(app, widget_id: str) -> str:
    try:
        return str(app.screen.query_one(f"#{widget_id}", Static).render())
    except Exception:
        return ""


async def _open_detail_from_dashboard(app, pilot) -> None:
    """Pano 'Popüler' tablosundan enter ile detay acar (THYAO)."""
    await wait_for(app, lambda: _row_count(app, "popular-table") == 3)
    table = app.screen.query_one("#popular-table", DataTable)
    table.move_cursor(row=0, column=0)
    await pilot.press("enter")
    await wait_for(app, lambda: isinstance(app.screen, DetailScreen))


# ----------------------------------------------------------------------
# Ekran testleri (run_test + pilot)
# ----------------------------------------------------------------------
def test_detail_renders_info_chart_news(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            assert app.screen.ticker == "THYAO"
            # Bilgi satiri: longName + sektor + fiyat + Δ%
            await wait_for(app, lambda: "Türk Hava Yolları" in _text(app, "detail-info"))
            info = _text(app, "detail-info")
            assert "Havacılık" in info
            assert "313,40" in info
            assert "+0,93%" in info
            # Buyuk grafik: ccharts CChartLine — show_prices/show_times etiketleri
            # ccharts tarafindan cizilir (TR format yok — noktali ondalik).
            await wait_for(app, lambda: "2026-07-01" in _text(app, "detail-chart"))
            chart_out = _text(app, "detail-chart")
            assert "313.40" in chart_out  # show_prices: max fiyat (noktali ondalik)
            assert "2026-07-03" in chart_out  # show_times: son tarih
            assert any(ch in chart_out for ch in "▁▂▃▄▅▆▇█")
            # Grafik basligi: tip + period (min/son/max artik ccharts etiketlerinde).
            title = _text(app, "chart-title")
            assert "GRAFİK (1 Ay · çizgi)" in title
            assert "en yüksek" not in title
            # Haberler (JWT)
            await wait_for(app, lambda: "THYAO haberi" in _text(app, "detail-news"))
            news = _text(app, "detail-news")
            assert "THYAO ikinci haber" in news
            assert "https://example.com" in news
            # Ust bar
            assert "AÇIK" in _text(app, "detail-status")

    asyncio.run(run())


def test_detail_period_change_refetches_with_new_period(make_app):
    seen: dict[str, list[str | None]] = {"periods": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/price/history/" in path:
            seen["periods"].append(request.url.params.get("period"))
            return httpx.Response(200, json=MOCK_HISTORY)
        return make_handler()(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            await wait_for(app, lambda: "2026-07-01" in _text(app, "detail-chart"))
            # '3' -> 3mo; period degisince aninda yeniden fetch (poll beklenmez)
            await pilot.press("3")
            await wait_for(app, lambda: "3mo" in seen["periods"])
            assert app.screen.period == "3mo"
            await wait_for(app, lambda: "GRAFİK (3 Ay · çizgi)" in _text(app, "chart-title"))
            # Ayni period'a tekrar basmak yeniden istek atmaz
            before = len(seen["periods"])
            await pilot.press("3")
            await asyncio.sleep(0.1)
            assert len(seen["periods"]) == before

    asyncio.run(run())


def test_detail_news_hidden_without_auth(make_app):
    async def run() -> None:
        app = make_app(make_handler(), authenticated=False)
        async with app.run_test(size=(120, 40)):
            app.open_detail("THYAO")
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            await wait_for(app, lambda: "Haberler için giriş yapın" in _text(app, "detail-news"))
            assert "fl auth login" in _text(app, "detail-news")
            # Public kisim (fiyat/grafik) auth'suz calisir
            await wait_for(app, lambda: "THYAO" in _text(app, "detail-info"))
            await wait_for(app, lambda: "2026-07-01" in _text(app, "detail-chart"))

    asyncio.run(run())


def test_detail_empty_history_shows_veri_yok(make_app):
    async def run() -> None:
        app = make_app(make_handler(history=[]))
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            await wait_for(app, lambda: "bu dönem için veri yok" in _text(app, "chart-title"))
            assert "Veri yok" in _text(app, "detail-chart")
            # Bilgi satiri ve haberler etkilenmez (kismi hata toleransi)
            await wait_for(app, lambda: "Türk Hava Yolları" in _text(app, "detail-info"))

    asyncio.run(run())


def test_detail_escape_returns_to_previous_screen(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            await wait_for(app, lambda: "THYAO" in _text(app, "detail-info"))
            await pilot.press("escape")
            await wait_for(app, lambda: isinstance(app.screen, DashboardScreen))

    asyncio.run(run())


def test_detail_chart_toggle_line_candle(make_app):
    """``c`` — line/candle toggle; veri cache'te oldugundan yeni istek YOK (P6).

    Titreşimli render: her ``c`` isabetinde ``_last_snapshot``'tan aninda
    cizilir (poll worker'a ihtiyac yok); istek sayisi degismez.
    """
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/price/history/" in request.url.path:
            calls["n"] += 1
        return make_handler(history=OHLC_HISTORY)(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            # Ilk durum: line (varsayilan)
            await wait_for(app, lambda: "2026-07-01" in _text(app, "detail-chart"))
            assert "GRAFİK (1 Ay · çizgi)" in _text(app, "chart-title")
            assert "▁" in _text(app, "detail-chart")
            before = calls["n"]
            # c -> candle: wick (│) cikar, baslik 'mum' gosterir
            await pilot.press("c")
            await wait_for(app, lambda: "│" in _text(app, "detail-chart"))
            assert "GRAFİK (1 Ay · mum)" in _text(app, "chart-title")
            assert calls["n"] == before  # cache — ek istek yok
            # c -> line: blok karakterler geri gelir (│ kaybolur)
            await pilot.press("c")
            await wait_for(app, lambda: "▁" in _text(app, "detail-chart") and "│" not in _text(app, "detail-chart"))
            assert "GRAFİK (1 Ay · çizgi)" in _text(app, "chart-title")
            assert calls["n"] == before

    asyncio.run(run())


def test_detail_default_chart_reads_tui_default_chart_config(make_app, tmp_path):
    """Config ``tui_default_chart = "candle"`` -> detay mum grafikle acilir (P6)."""
    (tmp_path / "config.toml").write_text('[cli]\ntui_default_chart = "candle"\n', encoding="utf-8")

    async def run() -> None:
        app = make_app(make_handler(history=OHLC_HISTORY))
        async with app.run_test(size=(120, 40)) as pilot:
            app.open_detail("THYAO")
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            await wait_for(app, lambda: "│" in _text(app, "detail-chart"))
            assert app.screen._chart_type == "candle"
            assert "GRAFİK (1 Ay · mum)" in _text(app, "chart-title")
            # c ile line'a donulebilir (toggle her iki yonde calisir)
            await pilot.press("c")
            await wait_for(app, lambda: "▁" in _text(app, "detail-chart"))
            assert app.screen._chart_type == "line"

    asyncio.run(run())


def test_detail_default_chart_param(make_app):
    """``FlorenceTUI(default_chart=...)`` parametresi detay baslangic tipini belirler."""
    async def run() -> None:
        app = make_app(make_handler(history=OHLC_HISTORY), default_chart="candle")
        async with app.run_test(size=(120, 40)):
            app.open_detail("THYAO")
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            await wait_for(app, lambda: "│" in _text(app, "detail-chart"))
            assert app.screen.chart_type == "candle"
            assert "GRAFİK (1 Ay · mum)" in _text(app, "chart-title")

    asyncio.run(run())


def test_detail_priority_bindings_isolated_from_tabs(make_app):
    """Detay ekranindayken 1, 3, 6 tuslari ana sayfa sekmelerine gecmek yerine period'u degistirir."""
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/price/history/" in request.url.path:
            seen.append(request.url.params.get("period"))
            return httpx.Response(200, json=MOCK_HISTORY)
        return make_handler()(request)

    async def run() -> None:
        app = make_app(handler)
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))

            # 3 basinca DigestScreen'e gecmemeli, DetailScreen'de 3mo period secilmeli
            await pilot.press("3")
            await wait_for(app, lambda: app.screen.period == "3mo")
            assert isinstance(app.screen, DetailScreen)

            # 6 basinca EconomyScreen'e gecmemeli, DetailScreen'de 6mo period secilmeli
            await pilot.press("6")
            await wait_for(app, lambda: app.screen.period == "6mo")
            assert isinstance(app.screen, DetailScreen)

            # 1 basinca DashboardScreen'e gecmemeli, DetailScreen'de 1mo period secilmeli
            await pilot.press("1")
            await wait_for(app, lambda: app.screen.period == "1mo")
            assert isinstance(app.screen, DetailScreen)

    asyncio.run(run())


def test_detail_button_clicks_period_and_type(make_app):
    """Fare ile butonlara tiklandiginda period ve cizgi/mum grafik turu aninda degisir."""
    async def run() -> None:
        app = make_app(make_handler(history=OHLC_HISTORY))
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            await wait_for(app, lambda: "2026-07-01" in _text(app, "detail-chart"))

            # [ 3A ] butonuna tikla
            btn_3mo = app.screen.query_one("#btn-period-3mo", Button)
            await pilot.click(btn_3mo)
            await wait_for(app, lambda: app.screen.period == "3mo")
            assert "btn-active" in btn_3mo.classes

            # [ 🕯️ Mum ] butonuna tikla
            btn_candle = app.screen.query_one("#btn-type-candle", Button)
            await pilot.click(btn_candle)
            await wait_for(app, lambda: "│" in _text(app, "detail-chart"))
            assert app.screen.chart_type == "candle"
            assert "btn-active" in btn_candle.classes

            # [ 📈 Çizgi ] butonuna tikla
            btn_line = app.screen.query_one("#btn-type-line", Button)
            await pilot.click(btn_line)
            await wait_for(app, lambda: "▁" in _text(app, "detail-chart"))
            assert app.screen.chart_type == "line"
            assert "btn-active" in btn_line.classes

    asyncio.run(run())


def test_detail_stats_card_renders_ohlc_and_52w(make_app):
    """OHLC istatistikleri ve 52H degerleri kartta dogru render edilir."""
    custom_company_info = {
        "THYAO": {
            "ticker": "THYAO",
            "longName": "Türk Hava Yolları",
            "sector": "Havacılık",
            "fiftyTwoWeekHigh": 350.0,
            "fiftyTwoWeekLow": 210.0,
            "summary": "Türkiye'nin bayrak taşıyıcı havayolu şirketi.",
        }
    }
    custom_prices = {
        "THYAO": {
            "ticker": "THYAO",
            "price": 313.4,
            "change_pct": 0.93,
            "open": 310.0,
            "high": 314.0,
            "low": 308.0,
            "previous_close": 310.0,
            "volume": 2500000000,
        }
    }

    async def run() -> None:
        app = make_app(make_handler(company_info=custom_company_info, prices=custom_prices))
        async with app.run_test(size=(120, 40)) as pilot:
            await _open_detail_from_dashboard(app, pilot)
            await wait_for(app, lambda: isinstance(app.screen, DetailScreen))
            await wait_for(app, lambda: "Açılış" in _text(app, "detail-stats"))

            stats = _text(app, "detail-stats")
            assert "310,00 ₺" in stats
            assert "314,00 ₺" in stats
            assert "308,00 ₺" in stats
            assert "2.50 Mr" in stats
            assert "210,00 - 350,00 ₺" in stats

            # Profil ozeti
            profile = _text(app, "detail-profile")
            assert "Türkiye'nin bayrak taşıyıcı" in profile

    asyncio.run(run())


def test_fl_tui_command_registered(tmp_path, monkeypatch):
    """``fl tui`` CLI komutu kayitli ve --help calisiyor (smoke)."""
    # Gercek kullanici config/token store'una dokunma.
    monkeypatch.setenv("FLORENCE_KEYRING", "0")
    monkeypatch.setenv("FLORENCE_TOKEN_STORE_PATH", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    from florence.cli.app import _run

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _run(["tui", "--help"], prog_name="fl")
    assert code == 0
    assert "tui" in out.getvalue().lower()


# ----------------------------------------------------------------------
# DataHub.fetch_detail birim testleri
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


def test_fetch_detail_fetches_all_with_token():
    async def run() -> None:
        hub = _hub(make_handler())
        snap = await hub.fetch_detail("THYAO", "3mo")
        assert snap.ticker == "THYAO"
        assert snap.period == "3mo"
        assert snap.market_status is not None
        assert snap.company_info is not None
        assert snap.company_info["longName"] == "Türk Hava Yolları"
        assert snap.current_price is not None
        assert snap.current_price["price"] == 313.4
        assert snap.price_history == MOCK_HISTORY
        assert snap.news is not None and snap.news[0]["title"] == "THYAO haberi"
        assert snap.auth_sections == ()
        assert not snap.errors

    asyncio.run(run())


def test_fetch_detail_news_auth_skip_without_token():
    async def run() -> None:
        hub = _hub(make_handler(), authenticated=False)
        snap = await hub.fetch_detail("THYAO", "1mo")
        # Public alanlar dolu; haberler bilincli atlanir (istek yok).
        assert snap.company_info is not None
        assert snap.current_price is not None
        assert snap.price_history == MOCK_HISTORY
        assert snap.news is None
        assert snap.auth_sections == ("news",)
        assert not snap.errors

    asyncio.run(run())


def test_fetch_detail_tolerates_section_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/companies/info/THYAO"):
            return httpx.Response(500, json={"detail": "error_internal"})
        if "/news/" in path:
            return httpx.Response(500, json={"detail": "error_internal"})
        return make_handler()(request)

    async def run() -> None:
        hub = _hub(handler)
        snap = await hub.fetch_detail("THYAO", "1mo")
        # Hatali alanlar None; digerleri etkilenmez.
        assert snap.company_info is None
        assert "company_info" in snap.errors
        assert snap.current_price is not None
        assert snap.price_history == MOCK_HISTORY
        assert snap.news is None
        assert "news" in snap.errors
        assert snap.auth_sections == ()  # hata degil, bilincli atlama yok

    asyncio.run(run())


def test_fetch_detail_history_cached_per_period():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/price/history/" in request.url.path:
            calls["n"] += 1
        return make_handler()(request)

    async def run() -> None:
        hub = _hub(handler)
        await hub.fetch_detail("THYAO", "1mo")
        await hub.fetch_detail("THYAO", "1mo")  # cache'ten
        await hub.fetch_detail("THYAO", "3mo")  # yeni period -> yeni istek
        assert calls["n"] == 2  # 1mo bir kez, 3mo bir kez

    asyncio.run(run())
