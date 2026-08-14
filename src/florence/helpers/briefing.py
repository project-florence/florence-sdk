"""H3 — ``ticker_briefing``: ticker tek bakista (helpers-design.md Bolum 2.3).

Veri kaynaklari: ``current_price`` + ``company_info`` + ``price_history``
(sparkline = son 30 kapanis) + ``news`` = 4 backend cagrisi.

Kismi sonuc ilkesi: tek parcanin hatasi paketi dusurmez — ilgili alan
``None``/``[]`` olur. Kimlik hatasi (``AuthError``) asla sessizce yutulmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..errors import AuthError, FlorenceError
from ._util import _as_rows, _num, now_iso, upper_ticker
from .models import Company, NewsHeadline, Quote, TickerBriefing, Trend
from .news import _news_items

if TYPE_CHECKING:  # pragma: no cover
    from ..client import AsyncFlorenceClient, FlorenceClient

__all__ = ["ticker_briefing", "ticker_briefing_async"]

def _safe[T](fn: Callable[[], T]) -> T | None:
    """Kismi sonuc ilkesi: alan ureticisini hatalara karsi korur.

    ``AuthError`` yeniden firlatilir (kimlik hatasi altyapi hatasidir);
    diger ``FlorenceError``lar ``None`` olarak tolere edilir.
    """
    try:
        return fn()
    except AuthError:
        raise
    except FlorenceError:
        return None


def _quote(client: Any, ticker: str) -> Quote | None:
    data = client.market.current_price(ticker)
    if not isinstance(data, dict):
        return None
    price = _num(data.get("price"))
    if price is None:
        return None  # is_stale / islem yok
    change = _num(data.get("change_pct"))
    if change is None:
        change = _num(data.get("change"))
    return Quote(
        price=price,
        change_pct=change,
        market_status=data.get("market_status") or data.get("status"),
    )


def _company(client: Any, ticker: str) -> Company | None:
    data = client.market.company_info(ticker)
    if not isinstance(data, dict):
        return None
    name = data.get("name") or data.get("longName") or data.get("company_name") or data.get("company")
    sector = data.get("sector") or data.get("industry") or data.get("sektor")
    return Company(name=name, sector=sector)


def _trend(client: Any, ticker: str, period: str) -> Trend | None:
    data = client.market.price_history(ticker, period=period, interval="1d")
    rows = _as_rows(data)
    closes = [c for c in (_num(row.get("close")) for row in rows) if c is not None]
    if len(closes) < 2:
        return None
    first, last = closes[0], closes[-1]
    change_pct = ((last - first) / first * 100.0) if first else None
    return Trend(period=period, change_pct=change_pct, sparkline=[round(c, 4) for c in closes[-30:]])


def _news(client: Any, ticker: str, amount: int) -> list[NewsHeadline]:
    data = client.market.news(ticker, amount=amount)
    return [
        NewsHeadline(title=item.get("title"), url=item.get("url"))
        for item in _news_items(data)[:amount]
        if item.get("url")
    ]


def ticker_briefing(
    client: FlorenceClient,
    ticker: str,
    news_amount: int = 3,
    trend_period: str = "1mo",
) -> TickerBriefing:
    """Ticker'i tek pakette ozetler: fiyat, profil, trend, son haberler."""
    t = upper_ticker(ticker)
    amount = max(1, min(int(news_amount), 10))
    quote = _safe(lambda: _quote(client, t))
    company = _safe(lambda: _company(client, t))
    trend = _safe(lambda: _trend(client, t, trend_period))
    news = _safe(lambda: _news(client, t, amount)) or []
    return TickerBriefing(
        ticker=t,
        generated_at=now_iso(),
        quote=quote,
        company=company,
        trend=trend,
        news=news,
    )


async def ticker_briefing_async(
    client: AsyncFlorenceClient,
    ticker: str,
    news_amount: int = 3,
    trend_period: str = "1mo",
) -> TickerBriefing:
    """``ticker_briefing``'in asenkron ikizi."""
    t = upper_ticker(ticker)
    amount = max(1, min(int(news_amount), 10))
    quote = _safe(lambda: _quote(client, t))
    company = _safe(lambda: _company(client, t))
    trend = _safe(lambda: _trend(client, t, trend_period))
    news = _safe(lambda: _news(client, t, amount)) or []
    return TickerBriefing(
        ticker=t,
        generated_at=now_iso(),
        quote=quote,
        company=company,
        trend=trend,
        news=news,
    )
