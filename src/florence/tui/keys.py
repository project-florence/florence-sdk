"""Tus haritasi sabitleri — ekranlar arasi tek kaynak (docs/tui-design.md §3.1).

``PERIODS`` detay ekraninin grafik period haritasidir; ``PERIOD_LABELS``
footer/goesterim etiketleridir. Degisiklikler yalnizca bu modulden
yapilir — ekranlar sabitlere atif yapar.
"""

#: Detay grafigi period haritasi: tus -> period (tasarim §5.4).
PERIODS: dict[str, str] = {"1": "1mo", "3": "3mo", "6": "6mo", "y": "1y"}

#: Period -> gorunur etiket.
PERIOD_LABELS: dict[str, str] = {
    "1mo": "1 Ay",
    "3mo": "3 Ay",
    "6mo": "6 Ay",
    "1y": "1 Yıl",
}

#: Varsayilan detay period'u (config ``tui_default_period`` yoksa).
DEFAULT_PERIOD = "1mo"

#: Detay grafigi tip haritasi: tip -> gorunur etiket (``c`` tusu ile toggle, P6).
CHART_LABELS: dict[str, str] = {"line": "çizgi", "candle": "mum"}

#: Varsayilan detay grafik tipi (config ``tui_default_chart`` yoksa).
DEFAULT_CHART = "line"

# ----------------------------------------------------------------------
# Global tuslar (app.py BINDINGS)
# ----------------------------------------------------------------------
KEY_QUIT = "q"
KEY_DASHBOARD = "1"
KEY_WATCHLIST = "2"
#: ``4`` — portfoy ekrani (Faz E, P7). ``p`` KULLANILMAZ (çakışma yok;
#: tui-design.md §3.1'deki v2 notu 4'ü öngörür).
KEY_PORTFOLIO = "4"
KEY_REFRESH = "r"
KEY_HELP = "h"

# ----------------------------------------------------------------------
# Pano tuslari (screens/dashboard.py BINDINGS)
# ----------------------------------------------------------------------
KEY_GAINERS = "g"
KEY_LOSERS = "l"
KEY_TOGGLE_MOVERS = "tab"
KEY_OPEN_DETAIL = "enter"

# ----------------------------------------------------------------------
# Detay tuslari (screens/detail.py kullanir)
# ----------------------------------------------------------------------
KEY_BACK = "escape"
KEY_FAVORITE = "f"
#: ``c`` — grafik tipi toggle (line <-> candle, P6).
KEY_CHART_TOGGLE = "c"

__all__ = [
    "CHART_LABELS",
    "DEFAULT_CHART",
    "DEFAULT_PERIOD",
    "KEY_BACK",
    "KEY_CHART_TOGGLE",
    "KEY_DASHBOARD",
    "KEY_FAVORITE",
    "KEY_GAINERS",
    "KEY_HELP",
    "KEY_LOSERS",
    "KEY_OPEN_DETAIL",
    "KEY_PORTFOLIO",
    "KEY_QUIT",
    "KEY_REFRESH",
    "KEY_TOGGLE_MOVERS",
    "KEY_WATCHLIST",
    "PERIOD_LABELS",
    "PERIODS",
]
