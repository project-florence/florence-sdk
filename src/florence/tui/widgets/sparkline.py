"""SparklineChart — Textual ``Sparkline`` sarmalayicisi (T-C3'te kaldirilacak).

Faz B (Y3) notu: saf yardimcilar (``normalize``, ``downsample``,
``spark_text``, ``SPARK_CHARS``, ``period_return``) ``tui/charts.py``'ye
tasindi — bu modul bunlari oradan yeniden export eder (``widgets/__init__.py``
ve eski cagrilar kesintisiz calisir). ``SparklineChart`` ve ``sparkline_color``
(``$success``/``$error``/``$foreground`` tema degiskeni) watchlist ccharts'a
gecse de detail ekrani Faz C'ye kadar bu widget'i kullandigi icin KALIR;
T-C3'te tüm dosya ile birlikte silinir.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from textual.app import ComposeResult
from textual.widgets import Sparkline, Static

from ..charts import (
    SPARK_CHARS,  # noqa: F401  # re-export (Y3)
    downsample,  # noqa: F401
    normalize,  # noqa: F401
    period_return,  # noqa: F401
    spark_text,  # noqa: F401
)

__all__ = [
    "SPARK_CHARS",
    "SparklineChart",
    "downsample",
    "normalize",
    "period_return",
    "spark_text",
    "sparkline_color",
]


def sparkline_color(return_value: float | None) -> str:
    """TR BIST renk kurali: yukari ``$success`` / asagi ``$error`` / duz gri."""
    if return_value is None or return_value == 0:
        return "$foreground"
    return "$success" if return_value > 0 else "$error"


class SparklineChart(Static):
    """Textual ``Sparkline`` sarmalayicisi: normalize + downsample + renk.

    Kullanim (watchlist/detay — PART 2):
        chart = SparklineChart()
        chart.update_data(close_values)
    """

    def __init__(
        self,
        values: Sequence[float | None] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._spark = Sparkline()
        self._values: list[float] = []
        if values:
            self.update_data(values)

    def compose(self) -> ComposeResult:
        yield self._spark

    @property
    def values(self) -> list[float]:
        """Normalize edilmis son veri (testler/gerekirse)."""
        return self._values

    def update_data(self, values: Sequence[float | None]) -> None:
        """Seriyi normalize edip cizer; renk donem getirisine baglanir."""
        self._values = normalize(values)
        self._spark.data = self._values
        self._apply_color(period_return(values))
        self.refresh()

    def on_mount(self) -> None:
        # Mount sonrasi tema hazir oldugundan renk tekrar uygulanir.
        self._apply_color(period_return(self._values) if self._values else None)

    def _apply_color(self, return_value: float | None) -> None:
        color = sparkline_color(return_value)
        resolved = self._resolve_theme(color)
        if isinstance(resolved, str):
            # Textual 8.x Sparkline renkleri Color nesnesi bekler; tema
            # degiskenleri hex string doner — parse et.
            try:
                from textual.color import Color

                resolved = Color.parse(resolved)
            except Exception:
                resolved = None
        if resolved is None:
            return
        try:
            self._spark.min_color = resolved
            self._spark.max_color = resolved
        except Exception:  # pragma: no cover — tema/renk ayrintilari
            pass

    def _resolve_theme(self, var: str) -> Any | None:
        """``$success`` benzeri tema degiskenini hex renge cevirir."""
        if var.startswith("$"):
            try:
                if self.is_mounted:
                    return self.app.theme_variables.get(var[1:])
            except AttributeError:
                return None
        return var