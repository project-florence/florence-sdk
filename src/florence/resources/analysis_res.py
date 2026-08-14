"""Analiz endpoint'leri: simülasyonlar, raporlar, hisse eslestirme (stocks/fit).

- Simülasyonlar: Monte Carlo tabanli; maliyet = gun * 0.005 kredi.
- Raporlar: generate (kredi harcar), search, history, download (md|docx|pdf).
- ``download_report`` ham dosya icerigi dondurur (raw cikti istisnasi).
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["AnalysisResource"]


class AnalysisResource(BaseResource):
    # ------------------------------------------------------------------
    # Simulations
    # ------------------------------------------------------------------
    """GET /simulations/per-day-cost — gunluk simulasyon maliyeti (JWT)."""

    def per_day_cost(self) -> Any:
        return self._request("GET", "/simulations/per-day-cost")

    """GET /simulations/estimate-cost/{ticker} — maliyet tahmini (JWT, ``?days=1..370``)."""

    def estimate_cost(self, ticker: str, days: int) -> Any:
        return self._request(
            "GET",
            f"/simulations/estimate-cost/{ticker}",
            params={"days": days},
        )

    """GET /simulations/history — simulasyon gecmisi (JWT; limit<=100)."""

    def simulation_history(self, limit: int = 20, offset: int = 0) -> Any:
        return self._request(
            "GET",
            "/simulations/history",
            params={"limit": limit, "offset": offset},
        )

    """GET /simulations/history/{sim_id} — tek simulasyon detayi (JWT)."""

    def simulation_detail(self, sim_id: int) -> Any:
        return self._request("GET", f"/simulations/history/{sim_id}")

    """GET /simulations/{ticker} — simulasyon calistir (JWT; kredi harcar).

    ``days`` zorunlu (1..370), ``bounds`` default "0.05", ``target`` opsiyonel.
    Yanit: ``{prob_above, prob_below, confidence, direction, simulation_id, ...}``.
    """

    def simulate(
        self,
        ticker: str,
        days: int,
        bounds: str = "0.05",
        target: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {"days": days, "bounds": bounds}
        if target is not None:
            params["target"] = target
        return self._request("GET", f"/simulations/{ticker}", params=params)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    """POST /reports/generate — rapor uret (JWT; kredi harcar, job-slot 900s).

    ``type``: quick_report|deep_report. ``purpose``: kullanicinin sorusu (opsiyonel).
    Yanit: ``{success, report_id, credits_spend, remaining_credits, report(md), ...}``.
    """

    def generate_report(
        self,
        ticker: str,
        type: str,
        purpose: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {"ticker": ticker, "type": type}
        if purpose is not None:
            params["purpose"] = purpose
        return self._request("POST", "/reports/generate", params=params)

    """GET /reports/info — rapor maliyetleri + endpoint dokumantasyonu."""

    def report_info(self) -> Any:
        return self._request("GET", "/reports/info")

    """GET /reports/history — rapor gecmisi (JWT; sort/order allowlist'li)."""

    def report_history(self, sort: str = "created_at", order: str = "desc") -> Any:
        return self._request(
            "GET",
            "/reports/history",
            params={"sort": sort, "order": order},
        )

    """GET /reports/search — raporlarda ara (JWT; ``?q=`` title/content ILIKE)."""

    def search_reports(
        self,
        q: str,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> Any:
        return self._request(
            "GET",
            "/reports/search",
            params={"q": q, "sort": sort, "order": order, "limit": limit, "offset": offset},
        )

    """GET /reports/{report_id} — tek rapor (JWT; owner-only, markdown icerik)."""

    def get_report(self, report_id: int) -> Any:
        return self._request("GET", f"/reports/{report_id}")

    """POST /reports/download — raporu indir (JWT; ``?report_id=&ftype=md|docx|pdf``).

    RAW CIKTI ISTISNASI: dosya icerigini (bytes) dondurur; ``dest_path``
    verilirse icerik dosyaya yazilir ve yol dondurulur.
    """

    def download_report(
        self,
        report_id: int,
        ftype: str,
        dest_path: str | None = None,
    ) -> Any:
        response = self._request(
            "POST",
            "/reports/download",
            params={"report_id": report_id, "ftype": ftype},
            raw=True,
        )
        content = response.content
        if dest_path:
            with open(dest_path, "wb") as f:
                f.write(content)
            return dest_path
        return content

    # ------------------------------------------------------------------
    # Fit / advisor
    # ------------------------------------------------------------------
    """POST /stocks/fit — profil kriterlerine gore hisse eslestir (JWT + advisor feature).

    Body: ``{horizon, profitability, risk_tolerance, limit}``
    (defaults: long, high, medium, 5).
    """

    def fit_stocks(
        self,
        horizon: str = "long",
        profitability: str = "high",
        risk_tolerance: str = "medium",
        limit: int = 5,
    ) -> Any:
        return self._request(
            "POST",
            "/stocks/fit",
            json={
                "horizon": horizon,
                "profitability": profitability,
                "risk_tolerance": risk_tolerance,
                "limit": limit,
            },
        )

    """POST /portfolio/profile — portfoye benzer hisseler (JWT + advisor).

    Body: ``{tickers: [1-50], limit}`` (ticker'lar buyuk harfe cevrilir).
    """

    def portfolio_profile(self, tickers: list[str], limit: int = 5) -> Any:
        return self._request(
            "POST",
            "/portfolio/profile",
            json={"tickers": tickers, "limit": limit},
        )
