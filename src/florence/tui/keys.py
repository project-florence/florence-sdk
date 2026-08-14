"""Tus haritasi sabitleri — ekranlar arasi tek kaynak (docs/tui-design.md §3.1).

``PERIODS`` detay ekraninin grafik period haritasidir (PART 2 kullanir);
``PERIOD_LABELS`` footer/goesterim etiketleridir. Degisiklikler yalnizca
bu modulden yapilir — ekranlar sabitlere atif yapar.
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

# ----------------------------------------------------------------------
# Global tuslar (app.py BINDINGS)
# ----------------------------------------------------------------------
KEY_QUIT = "q"
KEY_DASHBOARD = "1"
KEY_WATCHLIST = "2"
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
# Detay tuslari (PART 2 — screens/detail.py kullanir)
# ----------------------------------------------------------------------
KEY_BACK = "escape"
KEY_FAVORITE = "f"

__all__ = [
    "DEFAULT_PERIOD",
    "KEY_BACK",
    "KEY_DASHBOARD",
    "KEY_FAVORITE",
    "KEY_GAINERS",
    "KEY_HELP",
    "KEY_LOSERS",
    "KEY_OPEN_DETAIL",
    "KEY_QUIT",
    "KEY_REFRESH",
    "KEY_TOGGLE_MOVERS",
    "KEY_WATCHLIST",
    "PERIOD_LABELS",
    "PERIODS",
]
