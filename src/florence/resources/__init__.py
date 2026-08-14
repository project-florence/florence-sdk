"""Typed resource'lar — her endpoint grubu bir modul.

Kullanim (senkron):
    client = FlorenceClient()
    client.market.price_history("THYAO")

Kullanim (asenkron):
    client = AsyncFlorenceClient()
    await client.market.price_history("THYAO")

Standart cikti kurali ve sync/async davranisi icin ``base`` modulune bakin.
"""

from .analysis_res import AnalysisResource
from .auth_res import AuthResource
from .base import BaseResource
from .bots_res import BotsResource
from .economy_res import EconomyResource
from .export_res import ExportResource
from .market_res import MarketResource
from .misc_res import MiscResource
from .portfolio_res import PortfolioResource
from .user_res import UserResource

__all__ = [
    "AnalysisResource",
    "AuthResource",
    "BaseResource",
    "BotsResource",
    "EconomyResource",
    "ExportResource",
    "MarketResource",
    "MiscResource",
    "PortfolioResource",
    "UserResource",
]
