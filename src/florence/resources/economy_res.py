"""Ekonomi endpoint'leri: altin, gumus, platin, paladyum, doviz, makro.

Dikkat (backend pitfall): altin/doviz degerleri STRING'dir ve Turk virgullu
ondalik kullanir (``"40,25"``, ``"%0,42"``) — sayisal islem oncesi
``.replace(",", ".")`` ile cevirin.

NOT: backend middleware'i tum /api/v1'i korur — economy uclari allowlist'te
DEGIL, gecerli token ister (auth=True).
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["EconomyResource"]


class EconomyResource(BaseResource):
    """GET /economy/gold-prices — altin fiyatlari (16 kalem)."""

    def gold_prices(self) -> Any:
        return self._request("GET", "/economy/gold-prices")

    """GET /economy/silver-price — gumus fiyati. Yanit: ``{"gumus": ...}``."""

    def silver_price(self) -> Any:
        return self._request("GET", "/economy/silver-price")

    """GET /economy/gram-platinum-price — gram platin fiyati. Yanit: ``{"gram-platin": ...}``."""

    def platinum_price(self) -> Any:
        return self._request("GET", "/economy/gram-platinum-price")

    """GET /economy/gram-palladium-price — gram paladyum fiyati."""

    def palladium_price(self) -> Any:
        return self._request("GET", "/economy/gram-palladium-price")

    """GET /economy/currency — doviz kurlari (public; ``?symbols=USD,EUR`` filtresi)."""

    def currency(self, symbols: str | None = None) -> Any:
        params: dict[str, Any] = {}
        if symbols is not None:
            params["symbols"] = symbols
        return self._request("GET", "/economy/currency", params=params)

    """GET /macroeconomy — FRED makro serileri (14 seri, 24h cache)."""

    def macroeconomy(self) -> Any:
        return self._request("GET", "/macroeconomy")
