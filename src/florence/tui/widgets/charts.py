"""ccharts tabanli Textual widget'lari (CChartLine / CChartCandle).

SparklineChart'in yerini alir (plan v2 K2 revizyonu — Faz A T-A3). Static
alt sinifi: ``update_data(rows)`` -> ``ohlc_rows`` -> render -> ``Text``.
Textual 8.x Static.render() ANSI'yi kendisi cozmez — ``Text.from_ansi`` ile
donusturulur (renk korunur; tema degiskenleri adapter'da ANSI'ye cevrilir,
P4).

- Renk kaynagi: ``self.app.theme_variables`` (``$success``/``$error`` hex) —
  mount sonrasi ``on_mount``'ta ve her ``update_data``'da cozulur (tema hazir
  oldugunda). ``period_colors`` (TR BIST) ile eslestirilir ve
  ``single_color=True``'la cizilir (mevcut ``sparkline_color`` davranisi).
- Bos veri (``update_data([])``) -> ``Veri yok`` metni (widget kendi
  state'ini yonetir).
- Boyut: constructor ``width``/``height`` ile verilebilir; mount sonrasi
  widget'in kendi layout boyutu kullanilir (CSS kontrol eder).

Veri sözleşmesi: ``[{ts, open, high, low, close}, ...]`` — ``high``/``low``
yoksa adapter sentezler (P2). ccharts YALNIZCA ``tui/charts.py`` icinde
import edilir (Y2) — widget'lar adapter uzerinden gecer.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.widgets import Static

from .. import charts  # tui/charts.py — ccharts import'u yalnizca orada (Y2)

__all__ = ["CChartBase", "CChartCandle", "CChartLine"]

#: Varsayilan cizim boyutlari (CSS boyut vermezse; mount sonrasi layout kullanilir).
_DEFAULT_WIDTH = 40
_DEFAULT_HEIGHT = 8


class CChartBase(Static):
    """ccharts tabanli grafik widget'i (line/candle ortak davranis).

    ``_chart_type`` alt sinifta belirlenir (``"line"`` / ``"candle"``).
    """

    _chart_type: str = "line"

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        width: int | None = None,
        height: int | None = None,
        show_prices: bool = False,
        show_times: bool = False,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._width = width
        self._height = height
        self._show_prices = show_prices
        self._show_times = show_times
        self._rows: list[dict[str, Any]] = []
        self._rise: str | None = None
        self._fall: str | None = None

    @property
    def chart_type(self) -> str:
        return self._chart_type

    @chart_type.setter
    def chart_type(self, value: str) -> None:
        if value in ("line", "candle") and value != self._chart_type:
            self._chart_type = value
            self._apply_colors()
            self._render_chart()

    # ------------------------------------------------------------------
    # Yasam dongusu
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        # Tema mount sonrasi hazirdir — renkler cozulup geciktirilmis veri
        # varsa yeniden cizilir.
        self._apply_colors()
        if self._rows:
            self._render_chart()

    # ------------------------------------------------------------------
    # Publik API (Faz B/C ekranlari bunu cagirir)
    # ------------------------------------------------------------------
    def update_data(
        self,
        rows: list[dict[str, Any]] | None,
        *,
        chart_type: str | None = None,
        show_prices: bool | None = None,
        show_times: bool | None = None,
    ) -> None:
        """OHLC satirlarini cizer; bos liste ``Veri yok`` gosterir.

        ``rows`` kopyalanir — cagiran tarafin listesine dokunulmaz.
        ``chart_type`` (``"line"``/``"candle"``) verilirse ayni widget'ta
        cizim tipini degistirir (Faz C ``c`` toggle — P6); gecersiz deger
        yok sayilir, son gecerli tip korunur.
        """
        self._rows = [dict(r) for r in (rows or []) if isinstance(r, dict)]
        if chart_type in ("line", "candle"):
            self._chart_type = chart_type
        if show_prices is not None:
            self._show_prices = bool(show_prices)
        if show_times is not None:
            self._show_times = bool(show_times)
        self._apply_colors()
        self._render_chart()

    # ------------------------------------------------------------------
    # Renk (P4 kofrusu)
    # ------------------------------------------------------------------
    def _apply_colors(self) -> None:
        """Son verinin donem getirisine gore (rise, fall) ANSI renklerini cozer.

        Tema henuz hazir degilse veya tanimsizsa ``None`` kalir — ccharts
        kendi defaultunu (yesil/kirmizi) kullanir (fallback, P4).
        """
        theme = None
        try:
            if self.is_mounted and self.app is not None:
                theme = getattr(self.app, "theme_variables", None)
        except Exception:
            theme = None

        if self._chart_type == "candle":
            self._rise, self._fall = charts.candle_colors(theme)
        else:
            return_value = charts.period_return([row.get("close") for row in self._rows])
            self._rise, self._fall = charts.period_colors(return_value, theme)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _chart_dimensions(self) -> tuple[int, int]:
        """Cizim boyutu: mount sonrasi layout; degilse constructor degerleri."""
        if self.is_mounted and self.size.width > 2 and self.size.height > 2:
            return max(20, self.size.width - 2), max(3, self.size.height - 2)
        return self._width or _DEFAULT_WIDTH, self._height or _DEFAULT_HEIGHT

    def _render_chart(self) -> None:
        if not self._rows:
            self.update("Veri yok")
            return
        payload = charts.ohlc_rows(self._rows)
        width, height = self._chart_dimensions()
        if self._chart_type == "candle":
            kwargs: dict[str, Any] = {
                "single_color": False,
                "rise": self._rise,
                "fall": self._fall,
                "show_prices": self._show_prices,
                "show_times": self._show_times,
            }
            out = charts.render_candle(payload, width, height, **kwargs)
        else:
            kwargs = {
                "single_color": True,
                "rise": self._rise,
                "fall": self._fall,
                "show_prices": self._show_prices,
                "show_times": self._show_times,
            }
            out = charts.render_line(payload, width, height, **kwargs)
        # ccharts ciktisi ANSI ile islenmis — Text.from_ansi renkleri korur
        # (Textual Static ANSI'yi kendisi cozmez).
        self.update(Text.from_ansi(out) if out else "Veri yok")


class CChartLine(CChartBase):
    """Cizgi grafik widget'i — ``update_data(rows)`` ile cizim yapar."""

    _chart_type = "line"


class CChartCandle(CChartBase):
    """Mum grafigi widget'i — ``update_data(rows)`` ile cizim yapar."""

    _chart_type = "candle"