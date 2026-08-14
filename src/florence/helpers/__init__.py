"""Yardimci tool (helper) katmani — endpoint'lerin uzerine binen semantik kompozitler.

Tasarim: ``docs/helpers-design.md``. Tek niyet = tek cagri; CLI (``fl helper
...``) ve MCP (``helper_*``) ayni cekirdekten beslenir.

v1 seti (H1-H6):
- ``news_digest`` (H1): ticker haber ozeti + icerik
- ``fetch_article`` (H2): URL -> duz metin (SSRF korumali)
- ``ticker_briefing`` (H3): fiyat + profil + trend + haber tek pakette
- ``market_pulse`` (H4): piyasa durumu + kazananlar + kaybedenler
- ``portfolio_health`` (H5): portfoy deger/risk/performans ozeti
- ``macro_briefing`` (H6): doviz + altin + makro seriler

Her helper senkron + asenkron ikiz imzaya sahiptir (``news_digest`` /
``news_digest_async`` ...). Bos/kisa sonuc disiplini: 0 haber -> bos liste
(hata DEGIL); kismi hata -> ilgili alanda hata kodu, paket doner; yalnizca
altyapi hatasi (ag/kimlik) istisna firlatir.
"""

from __future__ import annotations

from ._http import ArticleFetchError, validate_fetch_url
from .article import fetch_article, fetch_article_async
from .briefing import ticker_briefing, ticker_briefing_async
from .macro import macro_briefing, macro_briefing_async
from .models import (
    Article,
    Benchmark,
    Company,
    Diversification,
    MacroBriefing,
    MarketPulse,
    NewsDigest,
    NewsDigestItem,
    NewsHeadline,
    PerformerRow,
    Performers,
    PortfolioHealth,
    PulseRow,
    Quote,
    Risk,
    TickerBriefing,
    Trend,
)
from .news import news_digest, news_digest_async
from .portfolio import portfolio_health, portfolio_health_async
from .pulse import market_pulse, market_pulse_async

__all__ = [
    "Article",
    "ArticleFetchError",
    "Benchmark",
    "Company",
    "Diversification",
    "MacroBriefing",
    "MarketPulse",
    "NewsDigest",
    "NewsDigestItem",
    "NewsHeadline",
    "PerformerRow",
    "Performers",
    "PortfolioHealth",
    "PulseRow",
    "Quote",
    "Risk",
    "TickerBriefing",
    "Trend",
    "fetch_article",
    "fetch_article_async",
    "macro_briefing",
    "macro_briefing_async",
    "market_pulse",
    "market_pulse_async",
    "news_digest",
    "news_digest_async",
    "portfolio_health",
    "portfolio_health_async",
    "ticker_briefing",
    "ticker_briefing_async",
    "validate_fetch_url",
]
