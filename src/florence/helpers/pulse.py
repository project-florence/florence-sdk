"""H4 — ``market_pulse``: piyasa ne durumda (helpers-design.md Bolum 2.4).

Veri kaynaklari: ``market_status`` + ``companies_summary`` (gainers/losers/
volume) + ``stats_top`` = 5 backend cagrisi — TAMAMI public (kimliksiz calisir).

Piyasa kapaliysa ``market_open: false`` + ``next_open_at``; listeler yine
doner (son islem gunu verisi). Hic veri yoksa bos listeler — hata DEGIL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..errors import AuthError, FlorenceError
from ._util import _as_rows, _num, now_iso
from .models import MarketPulse, PulseRow

if TYPE_CHECKING:  # pragma: no cover
    from ..client import AsyncFlorenceClient, FlorenceClient

__all__ = ["market_pulse", "market_pulse_async"]

def _safe[T](fn: Callable[[], T]) -> T | None:
    """Alan ureticisini korur: AuthError yeniden firlatilir, digerleri ``None``."""
    try:
        return fn()
    except AuthError:
        raise
    except FlorenceError:
        return None


def _summary_rows(client: Any, sort: str, limit: int) -> list[PulseRow]:
    data = client.market.companies_summary(limit=limit, sort=sort)
    rows: list[PulseRow] = []
    for row in _as_rows(data):
        ticker = row.get("ticker") or row.get("symbol") or row.get("code")
        if not ticker:
            continue
        if sort == "volume":
            volume = _num(row.get("volume"))
            if volume is None:
                volume = _num(row.get("hacim"))
            rows.append(PulseRow(ticker=ticker, volume=volume))
        else:
            change = _num(row.get("change_pct"))
            if change is None:
                change = _num(row.get("change"))
            if change is None:
                change = _num(row.get("changePercent"))
            rows.append(PulseRow(ticker=ticker, change_pct=change))
    return rows[:limit]


def _most_popular(client: Any, limit: int) -> list[PulseRow]:
    data = client.market.stats_top(limit=limit)
    rows: list[PulseRow] = []
    for row in _as_rows(data):
        ticker = row.get("ticker") or row.get("symbol")
        if not ticker:
            continue
        count = _num(row.get("count"))
        if count is None:
            count = _num(row.get("views"))
        if count is None:
            count = _num(row.get("popularity"))
        rows.append(PulseRow(ticker=ticker, count=int(count) if count is not None else None))
    return rows[:limit]


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "evet")
    return None


def _build(client: Any, limit: int) -> MarketPulse:
    """Ortak kurulum (sync/async client ortak — resource cagrilari ayni isimde)."""
    status = _safe(lambda: client.market.market_status())
    status_dict = status if isinstance(status, dict) else {}
    gainers = _safe(lambda: _summary_rows(client, "gainers", limit)) or []
    losers = _safe(lambda: _summary_rows(client, "losers", limit)) or []
    volume = _safe(lambda: _summary_rows(client, "volume", limit)) or []
    popular = _safe(lambda: _most_popular(client, limit)) or []
    return MarketPulse(
        market_open=_as_bool(status_dict.get("open")),
        next_open_at=status_dict.get("next_open_at") if isinstance(status_dict.get("next_open_at"), str) else None,
        holiday=_as_bool(status_dict.get("holiday")),
        gainers=gainers,
        losers=losers,
        most_popular=popular,
        volume_leaders=volume,
        generated_at=now_iso(),
    )


def market_pulse(client: FlorenceClient, limit: int = 5) -> MarketPulse:
    """Piyasa ozeti: durum + kazananlar + kaybedenler + populer + hacim liderleri."""
    return _build(client, max(1, min(int(limit), 50)))


async def market_pulse_async(client: AsyncFlorenceClient, limit: int = 5) -> MarketPulse:
    """``market_pulse``'in asenkron ikizi."""
    return _build(client, max(1, min(int(limit), 50)))
