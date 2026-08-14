"""Sparkline birim testleri: normalizasyon, downsample, renk kurali (tasarim §5).

- min-max normalizasyon; duz seri (max == min) -> 0.5 (bolunme hatasi yok).
- eksik ``close`` (None) degerleri atilir.
- downsample: hedef nokta sayisina ornekleme; kisa seri aynen korunur.
- renk: donem getirisine gore yesil/kirmizi (TR BIST konvansiyonu).
"""

from __future__ import annotations

import asyncio

from florence.tui.widgets.sparkline import (
    SparklineChart,
    downsample,
    normalize,
    period_return,
    sparkline_color,
)


def test_normalize_min_max():
    assert normalize([10, 20, 30]) == [0.0, 0.5, 1.0]
    assert normalize([30, 20, 10]) == [1.0, 0.5, 0.0]


def test_normalize_flat_series_to_half():
    assert normalize([5, 5, 5]) == [0.5, 0.5, 0.5]
    assert normalize([1, 1]) == [0.5, 0.5]


def test_normalize_drops_none_values():
    assert normalize([None, 0, 100]) == [0.0, 1.0]
    assert normalize([None, None]) == []


def test_normalize_empty():
    assert normalize([]) == []


def test_downsample_keeps_short_series():
    assert downsample([1, 2, 3], 5) == [1, 2, 3]


def test_downsample_reduces_series():
    out = downsample(list(range(10)), 4)
    assert len(out) == 4
    assert out[0] == 0
    assert out[-1] == 6  # esit aralikli ornekleme (0, 2, 4, 6)


def test_downsample_zero_points():
    assert downsample([1, 2, 3], 0) == []


def test_period_return():
    assert period_return([1, 2, 3]) == 2.0
    assert period_return([3, 2, 1]) == -2.0
    assert period_return([5]) is None
    assert period_return([None, 1, 2]) == 1.0


def test_sparkline_color_tr_bist():
    assert sparkline_color(1.0) == "$success"
    assert sparkline_color(-1.0) == "$error"
    assert sparkline_color(0.0) == "$foreground"
    assert sparkline_color(None) == "$foreground"


def test_sparkline_chart_widget_updates():
    from textual.app import App, ComposeResult

    class T(App):
        def compose(self) -> ComposeResult:
            yield SparklineChart([1, 2, 3], id="spark")

    async def run() -> None:
        app = T()
        async with app.run_test(size=(40, 5)) as pilot:
            await pilot.pause(0.1)
            chart = app.query_one("#spark", SparklineChart)
            assert chart.values == [0.0, 0.5, 1.0]
            chart.update_data([3, 2, 1])  # dusus -> kirmizi
            assert chart.values == [1.0, 0.5, 0.0]

    asyncio.run(run())
