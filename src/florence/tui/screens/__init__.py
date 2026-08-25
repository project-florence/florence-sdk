"""TUI ekranlari (karar K3: ayri ``Screen`` siniflari)."""

from .dashboard import DashboardScreen
from .detail import DetailScreen
from .digest import DigestScreen
from .economy import EconomyScreen
from .portfolio import PortfolioScreen
from .stocks import StocksScreen
from .watchlist import WatchlistScreen

__all__ = [
    "DashboardScreen",
    "DetailScreen",
    "DigestScreen",
    "EconomyScreen",
    "PortfolioScreen",
    "StocksScreen",
    "WatchlistScreen",
]

