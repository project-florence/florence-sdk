"""H2 — ``fetch_article``: URL -> duz metin (helpers-design.md Bolum 2.2).

Senkron + asenkron ikiz imzalar; client gerekmez (harici cekim). Altyapi
hatasi (DNS/TLS/timeout) ``ArticleFetchError`` firlatir; semantik sonuclar
(404, engelli host, PDF, 2MB+) ``Article.error`` alaninda kod olarak doner
(sonuc nesnesi, hata degil).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._extract import clean_text, extract_html
from ._http import DEFAULT_TIMEOUT, fetch_page, fetch_page_async
from .models import Article

if TYPE_CHECKING:  # pragma: no cover
    from typing import Any

__all__ = ["fetch_article", "fetch_article_async"]


def _article_from_page(page: dict[str, Any], max_chars: int) -> Article:
    """Guvenli sayfa sonucundan ``Article`` uretir (sync/async ortak)."""
    url = page["url"]
    resolved = page.get("resolved_url") or url
    if page.get("error"):
        return Article(url=url, resolved_url=resolved, error=page["error"])
    html = page.get("html") or ""
    title, text = extract_html(html)
    text = clean_text(text)
    if not text:
        # Icerik cikarilamadi: JS-render/SPA veya bos sayfa (sonuc, hata degil).
        return Article(url=url, resolved_url=resolved, title=title, content_available=False, needs_js=True)
    limit = max(1, int(max_chars))
    truncated = len(text) > limit
    return Article(
        url=url,
        resolved_url=resolved,
        title=title,
        text=text[:limit],
        content_available=True,
        needs_js=False,
        truncated=truncated,
    )


def fetch_article(
    url: str,
    *,
    max_chars: int = 8000,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str | None = None,
) -> Article:
    """URL'deki makaleyi duz metin olarak ceker (SSRF korumali)."""
    page = fetch_page(url, timeout=timeout, user_agent=user_agent)
    return _article_from_page(page, max_chars)


async def fetch_article_async(
    url: str,
    *,
    max_chars: int = 8000,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str | None = None,
) -> Article:
    """URL'deki makaleyi duz metin olarak ceker (asenkron, SSRF korumali)."""
    page = await fetch_page_async(url, timeout=timeout, user_agent=user_agent)
    return _article_from_page(page, max_chars)
