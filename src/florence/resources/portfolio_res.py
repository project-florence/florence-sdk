"""Portfoy endpoint'leri: favorites, portfolios (CRUD + analizler), virtual_portfolio.

Analiz uclari (valuation, returns, risk, benchmark, ...) JWT gerektirir.
``export_csv`` ham CSV metni dondurur (JSON degil — raw cikti istisnasi).
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["PortfolioResource"]


class PortfolioResource(BaseResource):
    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------
    """POST /favorites/{ticker} — favori ekle (JWT, idempotent)."""

    def add_favorite(self, ticker: str) -> Any:
        return self._request("POST", f"/favorites/{ticker}")

    """DELETE /favorites/{ticker} — favori cikar (JWT)."""

    def remove_favorite(self, ticker: str) -> Any:
        return self._request("DELETE", f"/favorites/{ticker}")

    """GET /favorites — favori listesi (JWT)."""

    def favorites(self) -> Any:
        return self._request("GET", "/favorites")

    # ------------------------------------------------------------------
    # Portfolios CRUD
    # ------------------------------------------------------------------
    """POST /portfolios — portfoy olustur (JWT). Body: ``{name, initial_balance>0}``."""

    def create_portfolio(self, name: str, initial_balance: float) -> Any:
        return self._request(
            "POST",
            "/portfolios",
            json={"name": name, "initial_balance": initial_balance},
        )

    """GET /portfolios — portfoy listesi (JWT)."""

    def list_portfolios(self) -> Any:
        return self._request("GET", "/portfolios")

    """GET /portfolios/{portfolio_id} — tek portfoy (JWT)."""

    def get_portfolio(self, portfolio_id: str) -> Any:
        return self._request("GET", f"/portfolios/{portfolio_id}")

    """PUT /portfolios/{portfolio_id} — portfoyu yeniden adlandir (JWT)."""

    def rename_portfolio(self, portfolio_id: str, name: str) -> Any:
        return self._request("PUT", f"/portfolios/{portfolio_id}", json={"name": name})

    """DELETE /portfolios/{portfolio_id} — portfoyu sil (JWT)."""

    def delete_portfolio(self, portfolio_id: str) -> Any:
        return self._request("DELETE", f"/portfolios/{portfolio_id}")

    """POST /portfolios/{portfolio_id}/duplicate — islemleriyle kopyala (JWT)."""

    def duplicate_portfolio(self, portfolio_id: str, name: str) -> Any:
        return self._request(
            "POST",
            f"/portfolios/{portfolio_id}/duplicate",
            json={"name": name},
        )

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------
    """GET /portfolios/{portfolio_id}/transactions — islem listesi (JWT).

    Filtreler: ``ticker``, ``tx_type`` (alias: type), ``start``/``end`` (ISO).
    """

    def get_transactions(
        self,
        portfolio_id: str,
        ticker: str | None = None,
        tx_type: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {}
        if ticker is not None:
            params["ticker"] = ticker
        if tx_type is not None:
            params["tx_type"] = tx_type
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._request(
            "GET",
            f"/portfolios/{portfolio_id}/transactions",
            params=params,
        )

    """POST /portfolios/{portfolio_id}/transactions — islem ekle (JWT).

    Body: ``{ticker, type: BUY|SELL, quantity>0}``. Piyasa acik olmalidir
    (kapaliysa 400 ``"Market is closed"``). Fiyat piyasadan otomatik alinir.
    """

    def add_transaction(
        self,
        portfolio_id: str,
        ticker: str,
        type: str,
        quantity: float,
    ) -> Any:
        return self._request(
            "POST",
            f"/portfolios/{portfolio_id}/transactions",
            json={"ticker": ticker, "type": type, "quantity": quantity},
        )

    """PUT /portfolios/{portfolio_id}/transactions/{tx_id} — islem guncelle (JWT).

    Body: ``{price?, quantity?}`` (en az biri; manuel fiyat/guncelleme).
    """

    def update_transaction(
        self,
        portfolio_id: str,
        tx_id: str,
        price: float | None = None,
        quantity: float | None = None,
    ) -> Any:
        body: dict[str, Any] = {}
        if price is not None:
            body["price"] = price
        if quantity is not None:
            body["quantity"] = quantity
        return self._request(
            "PUT",
            f"/portfolios/{portfolio_id}/transactions/{tx_id}",
            json=body,
        )

    """DELETE /portfolios/{portfolio_id}/transactions/undo — son islemi geri al (JWT)."""

    def undo_transaction(self, portfolio_id: str) -> Any:
        return self._request("DELETE", f"/portfolios/{portfolio_id}/transactions/undo")

    # ------------------------------------------------------------------
    # Analizler
    # ------------------------------------------------------------------
    """GET /portfolios/{portfolio_id}/valuation — degerleme (JWT)."""

    def valuation(self, portfolio_id: str) -> Any:
        return self._request("GET", f"/portfolios/{portfolio_id}/valuation")

    """GET /portfolios/{portfolio_id}/diversification — cesitlendirme (JWT)."""

    def diversification(self, portfolio_id: str) -> Any:
        return self._request("GET", f"/portfolios/{portfolio_id}/diversification")

    """GET /portfolios/{portfolio_id}/performers — en iyi/en kotu (JWT, ``?top_n=``)."""

    def performers(self, portfolio_id: str, top_n: int = 5) -> Any:
        return self._request(
            "GET",
            f"/portfolios/{portfolio_id}/performers",
            params={"top_n": top_n},
        )

    """GET /portfolios/{portfolio_id}/history — deger gecmisi (JWT).

    ``period``: 1w|1mo|3mo|6mo|1y|max (default 1mo).
    """

    def history(self, portfolio_id: str, period: str = "1mo") -> Any:
        return self._request(
            "GET",
            f"/portfolios/{portfolio_id}/history",
            params={"period": period},
        )

    """GET /portfolios/{portfolio_id}/returns — getiri (JWT; abs/total/CAGR)."""

    def returns(self, portfolio_id: str, period: str = "1mo") -> Any:
        return self._request(
            "GET",
            f"/portfolios/{portfolio_id}/returns",
            params={"period": period},
        )

    """GET /portfolios/{portfolio_id}/risk — risk (JWT; volatility/drawdown/sharpe)."""

    def risk(self, portfolio_id: str, period: str = "1y") -> Any:
        return self._request(
            "GET",
            f"/portfolios/{portfolio_id}/risk",
            params={"period": period},
        )

    """GET /portfolios/{portfolio_id}/benchmark — XU100 karsilastirma (JWT, ``?ticker=``)."""

    def benchmark(self, portfolio_id: str, ticker: str = "XU100") -> Any:
        return self._request(
            "GET",
            f"/portfolios/{portfolio_id}/benchmark",
            params={"ticker": ticker},
        )

    """GET /portfolios/{portfolio_id}/performance — verimlilik skoru (JWT)."""

    def performance(self, portfolio_id: str) -> Any:
        return self._request("GET", f"/portfolios/{portfolio_id}/performance")

    """GET /portfolios/{portfolio_id}/stats — islem istatistikleri (JWT)."""

    def stats(self, portfolio_id: str) -> Any:
        return self._request("GET", f"/portfolios/{portfolio_id}/stats")

    """GET /portfolios/{portfolio_id}/snapshot — birlesik ozet (JWT)."""

    def snapshot(self, portfolio_id: str) -> Any:
        return self._request("GET", f"/portfolios/{portfolio_id}/snapshot")

    """GET /portfolios/{portfolio_id}/export/csv — CSV indirme (JWT).

    RAW CIKTI ISTISNASI: CSV metni dondurur (``response.text``), JSON degil.
    """

    def export_csv(self, portfolio_id: str) -> Any:
        response = self._request(
            "GET",
            f"/portfolios/{portfolio_id}/export/csv",
            raw=True,
        )
        return response.text
