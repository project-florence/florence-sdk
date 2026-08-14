"""Piyasa verisi endpoint'leri: BIST sirketleri, fiyat, haber, durum, istatistik.

Parametre adlari ve default'lari openapi.json'dan birebir alinmistir.

NOT (canli backend dogrulamasi 2026-08-14): backend middleware'i /api/v1'in
tamamini korur — yalnizca PUBLIC_PATHS allowlist'indeki uclar auth'suz calisir
(market/status, auth/*, legal, about, version, contact, maintenance,
contributors, export/download). Diger tum market uclari gecerli token ister.
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["MarketResource"]


class MarketResource(BaseResource):
    """GET /bist/companies — BIST sirket listesi (public)."""

    def companies(
        self,
        sort: str = "alphabetical",
        offset: int = 0,
        limit: int = 50,
    ) -> Any:
        return self._request(
            "GET",
            "/bist/companies",
            params={"sort": sort, "offset": offset, "limit": limit},
        )

    """GET /bist/tickers — BIST ticker listesi (public)."""

    def tickers(
        self,
        sort: str = "alphabetical",
        offset: int = 0,
        limit: int = 50,
    ) -> Any:
        return self._request(
            "GET",
            "/bist/tickers",
            params={"sort": sort, "offset": offset, "limit": limit},
        )

    """GET /companies/search — sirket ara (public, ``?query=``, alias destekli)."""

    def search_companies(self, query: str) -> Any:
        return self._request(
            "GET",
            "/companies/search",
            params={"query": query},
        )

    """GET /companies/info/{ticker} — yapilandirilmis sirket profili (public)."""

    def company_info(self, ticker: str) -> Any:
        return self._request("GET", f"/companies/info/{ticker}")

    """GET /companies/info/{ticker}/md — markdown sirket profili (public)."""

    def company_info_md(self, ticker: str) -> Any:
        return self._request("GET", f"/companies/info/{ticker}/md")

    """GET /companies/summary — sirket ozet tablosu (public).

    ``sort``: popular|alphabetical|gainers|losers|price_high|price_low|volume|market_cap.
    ``tickers``: virgulle ayrilmis filtre (opsiyonel).
    """

    def companies_summary(
        self,
        limit: int = 50,
        offset: int = 0,
        sort: str = "popular",
        tickers: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {"limit": limit, "offset": offset, "sort": sort}
        if tickers is not None:
            params["tickers"] = tickers
        return self._request("GET", "/companies/summary", params=params)

    """GET /news/{ticker} — hisse haberleri (JWT + news feature; 10/dk)."""

    def news(self, ticker: str, amount: int = 10) -> Any:
        return self._request(
            "GET",
            f"/news/{ticker}",
            params={"amount": amount},
        )

    """GET /price/current — anlik fiyat (public; ``?ticker=&interval=``).

    ``interval``: 5m|30m|1h|1d (default 5m).
    """

    def current_price(self, ticker: str, interval: str = "5m") -> Any:
        return self._request(
            "GET",
            "/price/current",
            params={"ticker": ticker, "interval": interval},
        )

    """GET /price/history/{ticker} — fiyat gecmisi (public).

    ``period``: 1d..max, ``interval``: 5m..3mo (interval/period kisitlari backend'de).
    """

    def price_history(self, ticker: str, period: str = "1mo", interval: str = "1d") -> Any:
        return self._request(
            "GET",
            f"/price/history/{ticker}",
            params={"period": period, "interval": interval},
        )

    """GET /market/status — piyasa durumu (public; 60s cache).

    Yanit: ``{open, next_open_at, holiday}``.
    """

    def market_status(self) -> Any:
        return self._request("GET", "/market/status", auth=False)

    """GET /stats/top — populer ticker'lar (public)."""

    def stats_top(self, limit: int = 50) -> Any:
        return self._request("GET", "/stats/top", params={"limit": limit})

    """GET /stats/{ticker} — ticker bazli sayaclar (public)."""

    def stats(self, ticker: str) -> Any:
        return self._request("GET", f"/stats/{ticker}")
