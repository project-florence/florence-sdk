"""SparklineChart — Textual ``Sparkline`` sarmalayicisi (karar K2).

- ``normalize``: ``price_history`` ``close`` serisini min-max ile ``[0,1]``'e
  ceker; duz seri (max == min) 0.5'e sabitlenir (bolunme hatasi yok).
  Eksik ``close`` (None) kayitlari atilir (backend ara tatil gunu bos birakir).
- ``downsample``: terminal genisligine gore ornekleme — her sutuna 1 nokta;
  kisa seri aynen korunur (tasarim §5.2).
- Renk: donem getirisine (ilk vs son close) gore yesil (yukari) / kirmizi
  (asagi) — TR BIST konvansiyonu (tasarim §5.3). Renkler tema degiskenlerinden
  gelir (``$success`` / ``$error``), dark/light temada otomatik uyum saglar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from textual.app import ComposeResult
from textual.widgets import Sparkline, Static

__all__ = [
    "SparklineChart",
    "downsample",
    "normalize",
    "period_return",
    "sparkline_color",
]


def normalize(values: Sequence[float | None]) -> list[float]:
    """Min-max normalizasyon: ``[0,1]``; duz seri -> 0.5; None degerler atilir."""
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return []
    lo = min(cleaned)
    hi = max(cleaned)
    if hi == lo:
        return [0.5] * len(cleaned)
    span = hi - lo
    return [(v - lo) / span for v in cleaned]


def downsample(values: Sequence[float], max_points: int) -> list[float]:
    """Seriyi en fazla ``max_points`` noktaya esit aralikli ornekler."""
    if max_points <= 0 or not values:
        return []
    n = len(values)
    if n <= max_points:
        return list(values)
    step = n // max_points
    return [values[i * step] for i in range(max_points)]


def period_return(values: Sequence[float | None]) -> float | None:
    """Donem getirisi: (son - ilk) close. Yetersiz veride ``None``."""
    cleaned = [float(v) for v in values if v is not None]
    if len(cleaned) < 2:
        return None
    return cleaned[-1] - cleaned[0]


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
