"""Sparkline birim testleri: renk kurali + SparklineChart widget (tasarim §5).

Faz B (Y3) notu: ``normalize``/``downsample``/``spark_text``/``period_return``
helpers ``charts.py``'ye tasindi (testleri ``test_charts.py``'de). Bu dosya
yalnizca sparkline'a ozgu kalanlari test eder: ``sparkline_color`` kurali ve
``SparklineChart`` widget'i (Faz C'de tamamen kaldirilacak — T-C3).

- renk: donem getirisine gore yesil/kirmizi (TR BIST konvansiyonu).
- widget: normalize edilmis veriyi cizer, guncellemelerde seri degisir.
"""

from __future__ import annotations

import asyncio

from florence.tui.widgets.sparkline import SparklineChart, sparkline_color


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