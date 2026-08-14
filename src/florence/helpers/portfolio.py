"""H5 — ``portfolio_health``: portfoy sagligi ozeti (helpers-design.md Bolum 2.5).

Veri kaynaklari: ``snapshot`` + ``performers`` + ``risk`` + ``benchmark`` +
``diversification`` = 5 backend cagrisi (tamamı JWT).

Bos/kisa davranis:
- Bos portfoy (backend 400) -> ``total_value: 0`` + bos performer listeleri.
- Tek analiz ucu basarisizsa ilgili alan ``None`` (kismi sonuc ilkesi).
- Portfoy YOKSA (404) -> helper GERCEK hata firlatir (exit 1).
- Kimlik yok (401) -> ``AuthError`` (asla sessizce yutulmaz).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..errors import AuthError, FlorenceAPIError, FlorenceError, NetworkError
from ._util import _num
from .models import Benchmark, Diversification, PerformerRow, Performers, PortfolioHealth, Risk

if TYPE_CHECKING:  # pragma: no cover
    from ..client import AsyncFlorenceClient, FlorenceClient

__all__ = ["portfolio_health", "portfolio_health_async"]

def _safe[T](fn: Callable[[], T]) -> T | None:
    """Kismi sonuc ilkesi: analiz alani ureticisini korur (AuthError disinda)."""
    try:
        return fn()
    except AuthError:
        raise
    except FlorenceError:
        return None


def _first_num(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return _num(value)
    return None


def _perf_rows(raw: Any) -> list[PerformerRow]:
    rows: list[PerformerRow] = []
    for row in raw or []:
        if isinstance(row, str):
            rows.append(PerformerRow(ticker=row))
        elif isinstance(row, dict):
            rows.append(
                PerformerRow(
                    ticker=row.get("ticker") or row.get("symbol") or row.get("code"),
                    return_pct=_first_num(row, "return_pct", "return", "change_pct", "returnPercent"),
                )
            )
    return rows


def _performers(client: Any, pid: str) -> Performers | None:
    data = client.portfolio.performers(pid, top_n=5)
    if not isinstance(data, dict):
        return None
    top_raw = data.get("top") or data.get("best") or data.get("gainers")
    bottom_raw = data.get("bottom") or data.get("worst") or data.get("losers")
    return Performers(top=_perf_rows(top_raw), bottom=_perf_rows(bottom_raw))


def _risk(client: Any, pid: str, period: str) -> Risk | None:
    data = client.portfolio.risk(pid, period=period)
    if not isinstance(data, dict):
        return None
    return Risk(
        volatility=_num(data.get("volatility")),
        max_drawdown=_first_num(data, "max_drawdown", "maxDrawdown", "drawdown"),
        sharpe=_first_num(data, "sharpe", "sharpe_ratio"),
    )


def _benchmark(client: Any, pid: str) -> Benchmark | None:
    data = client.portfolio.benchmark(pid, ticker="XU100")
    if not isinstance(data, dict):
        return None
    return Benchmark(
        ticker=data.get("ticker") or data.get("benchmark") or "XU100",
        portfolio_return_pct=_first_num(data, "portfolio_return_pct", "portfolio_return", "portfolio_pct"),
        benchmark_return_pct=_first_num(data, "benchmark_return_pct", "benchmark_return", "benchmark_pct"),
        diff_pct=_first_num(data, "diff_pct", "diff", "difference"),
    )


def _diversification(client: Any, pid: str) -> Diversification | None:
    data = client.portfolio.diversification(pid)
    if not isinstance(data, dict):
        return None
    return Diversification(
        stocks=_first_num(data, "stocks", "stock", "hisse"),
        forex=_first_num(data, "forex", "doviz"),
        metals=_first_num(data, "metals", "metal", "altin"),
    )


def _totals(client: Any, pid: str) -> tuple[float, float | None, float | None]:
    """``snapshot``'tan toplam degerler; 404 -> gercek hata, 400 -> tolerans."""
    try:
        snap = client.portfolio.snapshot(pid)
    except AuthError:
        raise
    except NetworkError:
        raise  # altyapi hatasi — sessizce yutulmaz
    except FlorenceAPIError as exc:
        if exc.status_code == 404:
            raise  # portfoy yok — gercek hata
        snap = None  # bos portfoy / diger 4xx -> 0 ile devam
    except FlorenceError:
        snap = None
    if not isinstance(snap, dict):
        return 0.0, None, None
    total = _first_num(snap, "total_value", "totalValue") or 0.0
    pnl = _first_num(snap, "pnl")
    pnl_pct = _first_num(snap, "pnl_pct", "pnlPercent", "pnl_pct_total")
    return float(total), pnl, pnl_pct


def portfolio_health(
    client: FlorenceClient,
    portfolio_id: str,
    risk_period: str = "1y",
) -> PortfolioHealth:
    """Portfoyu tek pakette ozetler: deger, kazanan/kaybeden, risk, benchmark."""
    pid = str(portfolio_id)
    total_value, pnl, pnl_pct = _totals(client, pid)
    performers = _safe(lambda: _performers(client, pid))
    risk = _safe(lambda: _risk(client, pid, risk_period))
    benchmark = _safe(lambda: _benchmark(client, pid))
    diversification = _safe(lambda: _diversification(client, pid))
    return PortfolioHealth(
        portfolio_id=pid,
        total_value=total_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        performers=performers,
        risk=risk,
        benchmark=benchmark,
        diversification=diversification,
    )


async def portfolio_health_async(
    client: AsyncFlorenceClient,
    portfolio_id: str,
    risk_period: str = "1y",
) -> PortfolioHealth:
    """``portfolio_health``'in asenkron ikizi."""
    pid = str(portfolio_id)
    total_value, pnl, pnl_pct = _totals(client, pid)
    performers = _safe(lambda: _performers(client, pid))
    risk = _safe(lambda: _risk(client, pid, risk_period))
    benchmark = _safe(lambda: _benchmark(client, pid))
    diversification = _safe(lambda: _diversification(client, pid))
    return PortfolioHealth(
        portfolio_id=pid,
        total_value=total_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        performers=performers,
        risk=risk,
        benchmark=benchmark,
        diversification=diversification,
    )
