"""ccharts tabanli Textual widget'larinin testleri (tasarim v2, Faz A — T-A3).

Strateji (plan §Test Stratejisi 2): widget'lar GERCEK ccharts ile render
eder (zorunlu dep — ImportError fail loud). Ekran render'i kilirgan string
eslesmesinden kacinir: karakter varligina dayanir (``▁`` blok, ``│`` wick,
``Veri yok``). ``app.theme_variables`` test dict'i ile mock'lanir (P4 —
gercek tema varyasyonu degil).

Kapsam (plan T-A3):
- ``CChartLine.update_data([{ts..close..}])`` -> ``render()`` ciktisinda
  unicode blok (``▁▂…█``) ve ``\\n`` var.
- ``CChartCandle`` -> ``│`` (wick) karakteri var.
- Bos veri (``update_data([])``) -> ``Veri yok`` metni.
- Tema renkleri ANSI'ye cevriliyor (spans'ta renk var).
"""

from __future__ import annotations

import asyncio

import pytest
from textual.app import App, ComposeResult

from florence.tui.widgets.charts import CChartCandle, CChartLine

#: MOCK_HISTORY benzeri 3 kayit (high/low yok -> sentez, P2).
MOCK_ROWS = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 300.0, "close": 310.0, "volume": 1000},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 310.0, "close": 313.4, "volume": 1200},
    {"ts": "2026-07-03T00:00:00+00:00", "open": 313.4, "close": 312.0, "volume": 900},
]

#: Mum wick'ini gosteren genis aralikli OHLC (high/low gercek).
MOCK_OHLC_ROWS = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 100.0, "high": 200.0, "low": 50.0, "close": 150.0},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 150.0, "high": 160.0, "low": 40.0, "close": 60.0},
]

#: P4 kofrusu icin test temasi (web rengi -> 24-bit ANSI).
TEST_THEME = {"success": "#1a8a5c", "error": "#dc322f"}


class _ChartApp(App[None]):
    """Tek grafik widget'i barindiran headless test uygulamasi."""

    def __init__(self, widget: CChartLine | CChartCandle) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _plain(chart: CChartLine | CChartCandle) -> str:
    """Render ciktisinin duz metni (ANSI/renksiz)."""
    return str(chart.render())


def _spans_are_colored(chart: CChartLine | CChartCandle) -> bool:
    """Render ciktisindaki span'larda renk var mi (ANSI kofrusu).

    Textual 8.x Static.render() icerigi ``textual.content.Content`` doner
    (Text sarmalayicisi) — ikisi de ``spans`` tasir; ``foreground`` renk
    tasir.
    """
    rendered = chart.render()
    spans = getattr(rendered, "spans", None)
    if not spans:
        return False
    return any(
        getattr(span.style, "foreground", None) is not None for span in spans
    )


def _run(coro) -> None:
    asyncio.run(coro)


# ----------------------------------------------------------------------
# CChartLine
# ----------------------------------------------------------------------
def test_cchart_line_renders_blocks_and_newlines():
    async def run() -> None:
        app = _ChartApp(CChartLine(id="line-chart"))
        async with app.run_test(size=(100, 20)) as pilot:
            chart = app.query_one("#line-chart", CChartLine)
            # Tema P4 kofrusu: gercek tema varyasyonu degil, test dict'i.
            app.theme_variables = dict(TEST_THEME)
            chart.update_data(MOCK_ROWS)
            content = _plain(chart)
            assert content
            assert "\n" in content
            # Unicode blok karakterleri cikar (ccharts line ciktisi).
            assert any(ch in content for ch in "▁▂▃▄▅▆▇█")
            # ANSI renkleri Text span'larina islendi (P4 kofrusu calisti).
            assert _spans_are_colored(chart)
            await pilot.pause(0.05)

    _run(run())


def test_cchart_line_shows_veri_yok_on_empty_data():
    async def run() -> None:
        app = _ChartApp(CChartLine(id="line-chart"))
        async with app.run_test(size=(100, 20)) as pilot:
            chart = app.query_one("#line-chart", CChartLine)
            chart.update_data([])
            assert "Veri yok" in _plain(chart)
            # Gecersiz satirlar da bos sayilir (hicbir close yok).
            chart.update_data([{"ts": "x", "close": None}])
            assert "Veri yok" in _plain(chart)
            await pilot.pause(0.05)

    _run(run())


def test_cchart_line_show_labels_flags():
    async def run() -> None:
        app = _ChartApp(
            CChartLine(id="line-chart", width=40, height=8, show_prices=True, show_times=True)
        )
        async with app.run_test(size=(100, 20)) as pilot:
            chart = app.query_one("#line-chart", CChartLine)
            chart.update_data(MOCK_ROWS)
            content = _plain(chart)
            # show_prices: ccharts noktali ondalik basar (TR format yok — not).
            assert "313.40" in content
            # show_times: ilk ISO tarihi.
            assert "2026-07-01" in content
            await pilot.pause(0.05)

    _run(run())


# ----------------------------------------------------------------------
# CChartCandle
# ----------------------------------------------------------------------
def test_cchart_candle_renders_wick_characters():
    async def run() -> None:
        app = _ChartApp(CChartCandle(id="candle-chart", width=40, height=8))
        async with app.run_test(size=(100, 20)) as pilot:
            chart = app.query_one("#candle-chart", CChartCandle)
            app.theme_variables = dict(TEST_THEME)
            chart.update_data(MOCK_OHLC_ROWS)
            content = _plain(chart)
            assert content
            assert "\n" in content
            # Mum wick karakteri (│) cikar.
            assert "│" in content
            assert _spans_are_colored(chart)
            await pilot.pause(0.05)

    _run(run())


def test_cchart_candle_shows_veri_yok_on_empty_data():
    async def run() -> None:
        app = _ChartApp(CChartCandle(id="candle-chart"))
        async with app.run_test(size=(100, 20)) as pilot:
            chart = app.query_one("#candle-chart", CChartCandle)
            chart.update_data([])
            assert "Veri yok" in _plain(chart)
            await pilot.pause(0.05)

    _run(run())


# ----------------------------------------------------------------------
# Ortak davranis
# ----------------------------------------------------------------------
def test_cchart_widgets_exposed_via_widgets_package():
    """widgets/__init__.py yeni siniflari export ediyor (Faz B/C importlari)."""
    from florence.tui.widgets import CChartCandle, CChartLine  # noqa: PLC0415

    assert issubclass(CChartLine, CChartLine)
    assert issubclass(CChartCandle, CChartCandle)


def test_cchart_update_data_replaces_previous_data():
    async def run() -> None:
        app = _ChartApp(CChartLine(id="line-chart"))
        async with app.run_test(size=(100, 20)) as pilot:
            chart = app.query_one("#line-chart", CChartLine)
            chart.update_data(MOCK_ROWS)
            first = _plain(chart)
            chart.update_data([])
            assert "Veri yok" in _plain(chart)
            chart.update_data(MOCK_OHLC_ROWS)  # yeniden veri -> tekrar render
            assert "Veri yok" not in _plain(chart)
            assert first != _plain(chart)
            await pilot.pause(0.05)

    _run(run())


@pytest.mark.parametrize("widget_cls", [CChartLine, CChartCandle])
def test_cchart_widgets_accept_kwargs(widget_cls):
    """Textual standart kwargs (name/id/classes) kabul edilir."""
    widget = widget_cls(name="g", id="c1", classes="x")
    assert widget.id == "c1"
    assert "x" in widget.classes
    assert widget.name == "g"