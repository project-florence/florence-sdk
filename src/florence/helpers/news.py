"""H1 — ``news_digest``: ticker haber ozeti + icerik (helpers-design.md Bolum 2.1).

- ``amount`` 1-10 araligina kirpilir (news 10/dk rate limiti).
- 0 haber -> ``items: []`` (hata DEGIL); N'den az -> ne varsa o.
- Tek URL cekilemezse (404/JS/engelli) o item ``fetch_error`` alir, digest
  doner (kismi sonuc ilkesi).
- Ana kaynak (``market.news``) 401/429 verirse helper GERCEK hata firlatir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._http import ArticleFetchError
from ._util import now_iso, upper_ticker
from .article import fetch_article, fetch_article_async
from .models import NewsDigest, NewsDigestItem

if TYPE_CHECKING:  # pragma: no cover
    from ..client import AsyncFlorenceClient, FlorenceClient

__all__ = ["news_digest", "news_digest_async"]


def _news_items(data: Any) -> list[dict[str, Any]]:
    """``market.news`` yanitindan haber dict'lerini cikarir (listeye toleransli)."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("news", "items", "results", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _build_items(
    raw_items: list[dict[str, Any]],
    *,
    fetch_content: bool,
    max_chars: int,
) -> list[NewsDigestItem]:
    """Haber satirlarini icerik cekimiyle birlestirir (senkron)."""
    items: list[NewsDigestItem] = []
    for raw in raw_items:
        title = raw.get("title")
        url = raw.get("url")
        published_at = raw.get("published_at")
        content: str | None = None
        available = False
        fetch_error: str | None = None
        if fetch_content:
            if not url:
                fetch_error = "no_url"
            else:
                try:
                    article = fetch_article(url, max_chars=max_chars)
                except ArticleFetchError:
                    fetch_error = "network"
                else:
                    if article.error:
                        fetch_error = article.error
                    elif not article.content_available:
                        fetch_error = "needs_js"
                    else:
                        content = article.text
                        available = True
        items.append(
            NewsDigestItem(
                title=title,
                url=url,
                published_at=published_at,
                content=content,
                content_available=available,
                fetch_error=fetch_error,
            )
        )
    return items


async def _build_items_async(
    raw_items: list[dict[str, Any]],
    *,
    fetch_content: bool,
    max_chars: int,
) -> list[NewsDigestItem]:
    """Haber satirlarini icerik cekimiyle birlestirir (asenkron)."""
    items: list[NewsDigestItem] = []
    for raw in raw_items:
        title = raw.get("title")
        url = raw.get("url")
        published_at = raw.get("published_at")
        content: str | None = None
        available = False
        fetch_error: str | None = None
        if fetch_content:
            if not url:
                fetch_error = "no_url"
            else:
                try:
                    article = await fetch_article_async(url, max_chars=max_chars)
                except ArticleFetchError:
                    fetch_error = "network"
                else:
                    if article.error:
                        fetch_error = article.error
                    elif not article.content_available:
                        fetch_error = "needs_js"
                    else:
                        content = article.text
                        available = True
        items.append(
            NewsDigestItem(
                title=title,
                url=url,
                published_at=published_at,
                content=content,
                content_available=available,
                fetch_error=fetch_error,
            )
        )
    return items


def news_digest(
    client: FlorenceClient,
    ticker: str,
    amount: int = 5,
    fetch_content: bool = True,
    max_chars: int = 6000,
) -> NewsDigest:
    """Ticker'in ilk N haberini, icerikleri duz metin olarak ceker.

    ``fetch_content=False`` -> saf liste modu (icerik cekimi yok).
    """
    t = upper_ticker(ticker)
    limit = max(1, min(int(amount), 10))
    data = client.market.news(t, amount=limit)
    items = _build_items(_news_items(data)[:limit], fetch_content=fetch_content, max_chars=max_chars)
    fetched = sum(1 for item in items if item.content_available)
    failed = sum(1 for item in items if item.fetch_error)
    return NewsDigest(
        ticker=t,
        generated_at=now_iso(),
        items=items,
        requested=limit,
        fetched=fetched,
        failed=failed,
    )


async def news_digest_async(
    client: AsyncFlorenceClient,
    ticker: str,
    amount: int = 5,
    fetch_content: bool = True,
    max_chars: int = 6000,
) -> NewsDigest:
    """``news_digest``'in asenkron ikizi."""
    t = upper_ticker(ticker)
    limit = max(1, min(int(amount), 10))
    data = await client.market.news(t, amount=limit)
    items = await _build_items_async(_news_items(data)[:limit], fetch_content=fetch_content, max_chars=max_chars)
    fetched = sum(1 for item in items if item.content_available)
    failed = sum(1 for item in items if item.fetch_error)
    return NewsDigest(
        ticker=t,
        generated_at=now_iso(),
        items=items,
        requested=limit,
        fetched=fetched,
        failed=failed,
    )
